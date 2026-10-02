"""Chiffrement EN FLUX des exports complets de la base (fichiers .adlexport).

Pourquoi un format à part (et pas celui des sauvegardes de boutique) ?
  - la clé n'est pas SAUVEGARDE_CLE mais une PHRASE SECRÈTE saisie par
    l'administrateur au moment de l'export : le fichier peut ainsi être
    ouvert sur un autre serveur (nouveau cluster MongoDB) ;
  - la base entière ne tient pas en mémoire sur le serveur Render gratuit
    (512 Mo) : on chiffre et déchiffre par blocs d'environ 1 Mo.

Format du fichier (tous les entiers en gros-boutiste) :
  En-tête (64 octets) :
    b"ADLYNEXP" (8) | version (1) | log2(N) scrypt (1) | r (1) | p (1)
    | taille des blocs en clair (4) | sel aléatoire (16) | vérificateur (32)
  Puis une suite de blocs :
    longueur du bloc chiffré (4) | drapeau (1 : 0 = bloc courant, 1 = dernier)
    | nonce aléatoire (12) | données chiffrées + étiquette GCM (16)

  - Clé : scrypt(phrase secrète, sel) -> 64 octets : les 32 premiers forment
    la clé AES-256-GCM, les 32 suivants le « vérificateur » écrit dans
    l'en-tête (il permet de dire « phrase secrète incorrecte » plutôt que
    « fichier abîmé », sans rien révéler de la clé).
  - Chaque bloc est authentifié avec, en données associées, l'en-tête complet,
    son NUMÉRO et son drapeau : un bloc déplacé, supprimé, dupliqué ou modifié,
    un fichier tronqué (pas de dernier bloc) ou rallongé est refusé.
  - Tous les blocs sauf le dernier contiennent exactement « taille des blocs »
    octets en clair : cela permet de relire le fichier dans n'importe quel
    ordre (le ZIP se lit en partant de la fin) sans jamais écrire le contenu
    déchiffré sur le disque.

La phrase secrète n'est JAMAIS stockée ni journalisée : sans elle, le fichier
est illisible et rien ne permet de la retrouver.
"""
from __future__ import annotations

import hmac
import io
import os
import struct
import unicodedata
from typing import BinaryIO, Callable, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIQUE = b"ADLYNEXP"
VERSION = 1
TAILLE_BLOC = 1024 * 1024  # 1 Mo de données en clair par bloc
# scrypt : N = 2^15, r = 8, p = 1 -> 32 Mo de mémoire, ~0,1 s par dérivation
SCRYPT_LOG2_N, SCRYPT_R, SCRYPT_P = 15, 8, 1
PHRASE_MIN = 12
PHRASE_MAX = 1024

_ENTETE = struct.Struct(">8sBBBBI16s32s")  # 64 octets
_BLOC = struct.Struct(">IB12s")  # 17 octets avant les données chiffrées
TAILLE_ENTETE = _ENTETE.size
ETIQUETTE = 16


class ErreurChiffrement(Exception):
    """Erreur lisible par l'administrateur (message en français)."""


class PhraseIncorrecte(ErreurChiffrement):
    pass


def valider_phrase(phrase: str, confirmation: Optional[str] = None) -> str:
    """Contrôle la phrase secrète saisie à l'export et la normalise (NFC : un
    « é » tapé sur deux claviers différents donne la même clé)."""
    phrase = unicodedata.normalize("NFC", phrase or "")
    if confirmation is not None and phrase != unicodedata.normalize("NFC", confirmation):
        raise ErreurChiffrement("Les deux phrases secrètes saisies ne sont pas identiques")
    if len(phrase) < PHRASE_MIN:
        raise ErreurChiffrement(f"La phrase secrète doit faire au moins {PHRASE_MIN} caractères")
    if len(phrase) > PHRASE_MAX:
        raise ErreurChiffrement("Phrase secrète trop longue")
    return phrase


def _deriver(phrase: str, sel: bytes, log2_n: int, r: int, p: int) -> tuple[bytes, bytes]:
    """Clé AES (32 octets) et vérificateur (32 octets) tirés de la phrase secrète."""
    brut = Scrypt(salt=sel, length=64, n=2 ** log2_n, r=r, p=p).derive(
        unicodedata.normalize("NFC", phrase).encode("utf-8"))
    return brut[:32], brut[32:]


def _aad(entete: bytes, index: int, drapeau: int) -> bytes:
    return entete + struct.pack(">QB", index, drapeau)


# ---------------------------------------------------------------------------
# Écriture
# ---------------------------------------------------------------------------
class EcrivainChiffre(io.RawIOBase):
    """Fichier en écriture seule : tout ce qui est écrit est découpé en blocs
    de TAILLE_BLOC, chiffrés au fil de l'eau. `fermer_flux()` écrit le dernier
    bloc (obligatoire : sans lui le fichier est considéré comme incomplet).

    Utilisable directement par zipfile (qui écrit alors en mode « flux »,
    sans revenir en arrière)."""

    def __init__(self, destination: BinaryIO, phrase: str, taille_bloc: int = TAILLE_BLOC):
        super().__init__()
        self._dest = destination
        self._taille_bloc = taille_bloc
        sel = os.urandom(16)
        cle, verificateur = _deriver(phrase, sel, SCRYPT_LOG2_N, SCRYPT_R, SCRYPT_P)
        self._aes = AESGCM(cle)
        self._entete = _ENTETE.pack(MAGIQUE, VERSION, SCRYPT_LOG2_N, SCRYPT_R, SCRYPT_P, taille_bloc, sel, verificateur)
        self._dest.write(self._entete)
        self._tampon = bytearray()
        self._index = 0
        self._position = 0  # octets en clair reçus (pour tell())
        self._termine = False

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def tell(self) -> int:
        return self._position

    def write(self, donnees) -> int:  # type: ignore[override]
        if self._termine:
            raise ValueError("Flux chiffré déjà fermé")
        donnees = bytes(donnees)
        self._tampon += donnees
        self._position += len(donnees)
        while len(self._tampon) >= self._taille_bloc:
            bloc = bytes(self._tampon[:self._taille_bloc])
            del self._tampon[:self._taille_bloc]
            self._ecrire_bloc(bloc, 0)
        return len(donnees)

    def _ecrire_bloc(self, clair: bytes, drapeau: int) -> None:
        nonce = os.urandom(12)
        chiffre = self._aes.encrypt(nonce, clair, _aad(self._entete, self._index, drapeau))
        self._dest.write(_BLOC.pack(len(chiffre), drapeau, nonce))
        self._dest.write(chiffre)
        self._index += 1

    def fermer_flux(self) -> None:
        """Écrit le dernier bloc (éventuellement vide). À appeler une seule fois."""
        if not self._termine:
            self._ecrire_bloc(bytes(self._tampon), 1)
            self._tampon.clear()
            self._termine = True
            self._dest.flush()


# ---------------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------------
def lire_entete(source: BinaryIO) -> dict:
    """Lit et contrôle l'en-tête (sans la phrase secrète)."""
    brut = source.read(TAILLE_ENTETE)
    if len(brut) < TAILLE_ENTETE or not brut.startswith(MAGIQUE):
        raise ErreurChiffrement("Ce fichier n'est pas un export adLyn (.adlexport)")
    magique, version, log2_n, r, p, taille_bloc, sel, verificateur = _ENTETE.unpack(brut)
    if version != VERSION:
        raise ErreurChiffrement(f"Version de fichier non prise en charge ({version})")
    # Bornes : un fichier fabriqué ne doit pas pouvoir épuiser la mémoire du serveur
    if not (10 <= log2_n <= 20 and 1 <= r <= 16 and 1 <= p <= 4 and 1024 <= taille_bloc <= 16 * 1024 * 1024):
        raise ErreurChiffrement("En-tête du fichier invalide")
    return {"brut": brut, "log2_n": log2_n, "r": r, "p": p, "taille_bloc": taille_bloc, "sel": sel,
            "verificateur": verificateur}


def ouvrir_cle(entete: dict, phrase: str) -> AESGCM:
    """Dérive la clé et vérifie la phrase secrète (PhraseIncorrecte sinon)."""
    cle, verificateur = _deriver(phrase, entete["sel"], entete["log2_n"], entete["r"], entete["p"])
    if not hmac.compare_digest(verificateur, entete["verificateur"]):
        raise PhraseIncorrecte("Phrase secrète incorrecte")
    return AESGCM(cle)


class LecteurChiffre(io.RawIOBase):
    """Lecture (avec retour en arrière) du contenu en clair d'un fichier chiffré.

    À l'ouverture, le fichier est entièrement parcouru et CHAQUE bloc est
    authentifié (fichier altéré, tronqué ou rallongé -> ErreurChiffrement),
    sans rien garder en mémoire. Ensuite, seul le bloc en cours de lecture
    est déchiffré en mémoire (environ 1 Mo)."""

    def __init__(self, chemin: str, phrase: str, progression: Optional[Callable[[int, int], None]] = None):
        super().__init__()
        self._f = open(chemin, "rb")  # noqa: SIM115 — fermé par close()
        try:
            self._entete = lire_entete(self._f)
            self._aes = ouvrir_cle(self._entete, phrase)
            self._taille_bloc = self._entete["taille_bloc"]
            self._pas = _BLOC.size + self._taille_bloc + ETIQUETTE  # place d'un bloc plein sur le disque
            self.taille = self._verifier(os.path.getsize(chemin), progression)
        except Exception:
            self._f.close()
            raise
        self._position = 0
        self._cache: tuple[int, bytes] = (-1, b"")

    def _dechiffrer(self, index: int) -> tuple[bytes, int]:
        brut = self._f.read(_BLOC.size)
        if len(brut) < _BLOC.size:
            raise ErreurChiffrement("Fichier incomplet (téléchargement interrompu ?)")
        longueur, drapeau, nonce = _BLOC.unpack(brut)
        if drapeau not in (0, 1) or longueur < ETIQUETTE or longueur > self._taille_bloc + ETIQUETTE:
            raise ErreurChiffrement("Fichier altéré : structure invalide")
        chiffre = self._f.read(longueur)
        if len(chiffre) < longueur:
            raise ErreurChiffrement("Fichier incomplet (téléchargement interrompu ?)")
        try:
            clair = self._aes.decrypt(nonce, chiffre, _aad(self._entete["brut"], index, drapeau))
        except InvalidTag as exc:
            raise ErreurChiffrement("Fichier altéré : son contenu a été modifié ou abîmé") from exc
        return clair, drapeau

    def _verifier(self, taille_fichier: int, progression) -> int:
        """Parcours complet : tous les blocs pleins, un seul dernier bloc, à la fin."""
        index, total = 0, 0
        while True:
            clair, drapeau = self._dechiffrer(index)
            if drapeau == 0 and len(clair) != self._taille_bloc:
                raise ErreurChiffrement("Fichier altéré : structure invalide")
            total += len(clair)
            index += 1
            if progression:
                progression(self._f.tell(), taille_fichier)
            if drapeau == 1:
                break
        if self._f.read(1):
            raise ErreurChiffrement("Fichier altéré : données en trop après la fin")
        return total

    # --- Interface « fichier » utilisée par zipfile ---
    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._position

    def seek(self, decalage: int, origine: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._position, io.SEEK_END: self.taille}[origine]
        self._position = max(0, base + decalage)
        return self._position

    def _bloc(self, index: int) -> bytes:
        if self._cache[0] != index:
            self._f.seek(TAILLE_ENTETE + index * self._pas)
            # Structure déjà contrôlée à l'ouverture : seule l'authenticité est revérifiée
            clair, _ = self._dechiffrer(index)
            self._cache = (index, clair)
        return self._cache[1]

    def readinto(self, tampon) -> int:  # type: ignore[override]
        if self._position >= self.taille:
            return 0
        index, decalage = divmod(self._position, self._taille_bloc)
        bloc = self._bloc(index)
        morceau = bloc[decalage:decalage + len(tampon)]
        tampon[:len(morceau)] = morceau
        self._position += len(morceau)
        return len(morceau)

    def read(self, taille: int = -1) -> bytes:  # type: ignore[override]
        """Lecture COMPLÈTE de `taille` octets (ou jusqu'à la fin) : zipfile
        suppose qu'une lecture renvoie tout ce qui est demandé."""
        if taille is None or taille < 0:
            taille = max(0, self.taille - self._position)
        morceaux, reste = [], taille
        while reste > 0:
            tampon = bytearray(min(reste, self._taille_bloc))
            n = self.readinto(tampon)
            if not n:
                break
            morceaux.append(bytes(tampon[:n]))
            reste -= n
        return b"".join(morceaux)

    def close(self) -> None:
        if not self.closed:
            self._f.close()
        super().close()
