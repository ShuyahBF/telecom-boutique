/*
  Actions d'une fiche de « Maintenance des équipements » (fiche déjà enregistrée) :
  - PHOTOS de l'équipement ou des pièces : ajout (JPEG / PNG, 5 Mo), annotation avant
    l'envoi (ImageAnnotator : flèches, cercles, texte, flou…), téléchargement, suppression ;
  - ENVOI PAR WHATSAPP au numéro de la fiche : modèle Meta approuvé (seul moyen d'écrire à
    un client qui n'a pas écrit au numéro adLyn dans les 24 h), ou message libre + photos ;
  - LIEN DE PAIEMENT Mobile Money (PawaPay), montant du diagnostic par défaut, payé ou non ;
  - FACTURER : boutique -> facture (brouillon) ou proforma dans « Factures & proformas » ;
    plateforme -> facture adLyn imprimable.
  API : <base>/{id}/photos | whatsapp | lien-paiement | facturer, et <base>/services.
*/
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient, messageErreur } from "@/lib/api";
import { prix } from "@/lib/format";
import { baseApi, lienImpression } from "@/lib/maintenanceEquipements";
import ImageAnnotator from "@/components/ImageAnnotator";
import Modal from "@/components/Modal";
import { useToast } from "@/components/Toast";

// ---- Photos -------------------------------------------------------------------------------
function Photos({ fiche, base, onChange }) {
  const toast = useToast();
  const [aAnnoter, setAAnnoter] = useState(null); // fichier choisi, en cours d'annotation
  const [envoi, setEnvoi] = useState(false);
  const entree = useRef(null);

  // Envoi de la photo (annotée ou non) au serveur
  const televerser = async (fichier) => {
    setEnvoi(true);
    try {
      const fd = new FormData();
      fd.append("fichier", fichier);
      await apiClient.post(`${base}/${fiche.id}/photos`, fd);
      toast.succes("Photo ajoutée");
      onChange();
    } catch (err) { toast.erreur(messageErreur(err, "Photo refusée")); }
    finally { setEnvoi(false); }
  };
  const supprimer = async (p) => {
    if (!window.confirm("Supprimer cette photo ?")) return;
    try { await apiClient.delete(`${base}/${fiche.id}/photos/${p.id}`); onChange(); }
    catch (err) { toast.erreur(messageErreur(err, "Suppression impossible")); }
  };
  const nbPhotos = (fiche.photos || []).length;

  return (
    <section className="space-y-2">
      <p className="text-sm font-semibold text-gray-800">📷 Photos de l'équipement / des pièces</p>
      <div className="flex flex-wrap gap-2">
        {(fiche.photos || []).map((p) => (
          <div key={p.id} className="w-24">
            <a href={p.url} target="_blank" rel="noreferrer"><img src={p.url} alt={p.nom} className="h-24 w-24 rounded-md object-cover ring-1 ring-gray-200" /></a>
            <div className="mt-0.5 flex justify-between text-sm">
              {/* Téléchargement de la photo (annotée) */}
              <a href={p.url} download={p.nom} target="_blank" rel="noreferrer" className="text-gray-500 hover:text-ink" title="Télécharger">⬇</a>
              <button type="button" onClick={() => supprimer(p)} className="text-red-500 hover:text-red-700" title="Supprimer">🗑</button>
            </div>
          </div>
        ))}
        {nbPhotos < 12 && (
          <button type="button" onClick={() => entree.current?.click()} disabled={envoi}
            className="flex h-24 w-24 flex-col items-center justify-center rounded-md border-2 border-dashed border-gray-300 text-xs text-gray-500 hover:border-primary">
            {envoi ? "Envoi…" : <><span className="text-xl">＋</span> Photo</>}
          </button>
        )}
        <input ref={entree} type="file" accept="image/jpeg,image/png" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) setAAnnoter(f); }} />
      </div>
      <p className="text-xs text-gray-500">JPEG ou PNG, 5 Mo au plus, 12 photos par fiche. Vous pouvez annoter la photo (flèches, cercles, texte, flou) avant de l'ajouter.</p>
      {aAnnoter && (
        <ImageAnnotator file={aAnnoter}
          onCancel={() => { const f = aAnnoter; setAAnnoter(null); if (window.confirm("Ajouter la photo sans annotation ?")) televerser(f); }}
          onDone={(annotee) => { setAAnnoter(null); televerser(annotee); }} />
      )}
    </section>
  );
}

// ---- Envoi par WhatsApp -------------------------------------------------------------------
function EnvoiWhatsApp({ fiche, base, services, onFermer, onEnvoye }) {
  const toast = useToast();
  const modeleDispo = services.modele_texte || services.modele_image;
  // Par défaut : le modèle Meta s'il existe (le client n'a probablement pas écrit au numéro adLyn)
  const [mode, setMode] = useState(modeleDispo ? "modele" : "texte");
  const [modele, setModele] = useState(services.modele_texte ? "texte" : "image");
  const [message, setMessage] = useState("");
  const [photos, setPhotos] = useState(true);
  const [lienPaiement, setLienPaiement] = useState(true);
  const [occupe, setOccupe] = useState(false);
  const nbPhotos = (fiche.photos || []).length;
  // Modèle à en-tête image choisi alors qu'aucune photo ne part avec la fiche
  const sansPhoto = mode === "modele" && modele === "image" && (!photos || !nbPhotos);

  const envoyer = async () => {
    setOccupe(true);
    try {
      const { data } = await apiClient.post(`${base}/${fiche.id}/whatsapp`, {
        mode, modele, message: message.trim() || null, photos, inclure_lien_paiement: lienPaiement,
      });
      if (data.non_envoye) toast.info(data.erreurs.join(" · "));
      else {
        toast.succes(`Fiche envoyée (${data.mode === "texte" ? "message libre" : "modèle Meta"}) — ${data.photos_envoyees} photo(s)`
          + (data.photos_non_envoyees ? `, ${data.photos_non_envoyees} à renvoyer quand le client aura répondu` : ""));
        if (data.erreurs?.length) toast.erreur(data.erreurs.join(" · "));
      }
      onEnvoye?.();
      onFermer();
    } catch (err) { toast.erreur(messageErreur(err, "Envoi impossible")); }
    finally { setOccupe(false); }
  };

  return (
    <Modal ouvert titre={`Envoyer la fiche ${fiche.numero} par WhatsApp`} onFermer={onFermer}>
      <div className="space-y-3 text-sm">
        <p className="text-gray-600">À : <b>{fiche.client_nom}</b> · {fiche.client_telephone || <span className="text-red-600">numéro manquant</span>}</p>
        <label className="flex items-center gap-2"><input type="checkbox" checked={photos} onChange={(e) => setPhotos(e.target.checked)} /> Joindre les photos ({nbPhotos})</label>
        {fiche.lien_paiement && !fiche.lien_paiement.paye && (
          <label className="flex items-center gap-2"><input type="checkbox" checked={lienPaiement} onChange={(e) => setLienPaiement(e.target.checked)} /> Ajouter le lien de paiement</label>
        )}

        {/* Modèle Meta : seul moyen d'écrire hors de la fenêtre de 24 h */}
        <label className={`block rounded-lg p-3 ring-1 ${mode === "modele" ? "ring-2 ring-primary" : "ring-gray-200"} ${modeleDispo ? "" : "opacity-60"}`}>
          <span className="flex items-center gap-2 font-semibold"><input type="radio" disabled={!modeleDispo} checked={mode === "modele"} onChange={() => setMode("modele")} /> Modèle WhatsApp approuvé</span>
          {modeleDispo ? (
            <span className="mt-2 flex flex-wrap gap-3 pl-6">
              {services.modele_texte && <span className="flex items-center gap-1"><input type="radio" checked={modele === "texte"} onChange={() => { setMode("modele"); setModele("texte"); }} /> Sans photo</span>}
              {services.modele_image && <span className="flex items-center gap-1"><input type="radio" checked={modele === "image"} onChange={() => { setMode("modele"); setModele("image"); }} /> Avec la 1re photo en en-tête</span>}
            </span>
          ) : <span className="mt-1 block pl-6 text-xs text-gray-500">Aucun modèle de fiche n'est encore approuvé sur la plateforme.</span>}
          {sansPhoto && (
            <span className="mt-2 block rounded bg-red-50 p-2 text-xs text-red-700">
              Ce modèle a un en-tête image, mais la fiche n'a aucune photo{nbPhotos ? " jointe (cochez « Joindre les photos »)" : ""}.
              Ajoutez une photo, ou choisissez le modèle sans photo.
            </span>
          )}
        </label>

        {/* Message libre : seulement si le client a écrit au numéro WhatsApp adLyn dans les 24 h */}
        <div className={`rounded-lg p-3 ring-1 ${mode === "texte" ? "ring-2 ring-primary" : "ring-gray-200"}`}>
          <label className="flex items-center gap-2 font-semibold"><input type="radio" checked={mode === "texte"} onChange={() => setMode("texte")} /> Message libre + photos</label>
          <p className="mt-1 pl-6 text-xs text-gray-500">Ne parvient au client que s'il a écrit au numéro WhatsApp d'adLyn dans les dernières 24 h (règle de Meta).</p>
          {mode === "texte" && (
            <textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} className="input mt-2"
              placeholder="Vide = résumé complet de la fiche (matériel, motif, diagnostic, pièces, équipe, prix…)" />
          )}
        </div>

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
          <button type="button" className="btn-primary bg-emerald-600 hover:bg-emerald-700" onClick={envoyer} disabled={occupe || !fiche.client_telephone || sansPhoto}>
            {occupe ? "Envoi…" : "Envoyer"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ---- Facturer ---------------------------------------------------------------------------
function Facturer({ fiche, base, espace, onFermer, onFacture }) {
  const toast = useToast();
  const [type, setType] = useState("FAC");
  const [lignes, setLignes] = useState([]);
  const [occupe, setOccupe] = useState(false);
  const total = (fiche.prix_diagnostic || 0) + lignes.reduce((s, l) => s + (Number(l.quantite) || 0) * (Number(l.prix_unitaire) || 0), 0);
  const majLigne = (i, champ, valeur) => setLignes(lignes.map((x, k) => (k === i ? { ...x, [champ]: valeur } : x)));

  const valider = async () => {
    setOccupe(true);
    try {
      const { data } = await apiClient.post(`${base}/${fiche.id}/facturer`, {
        type_document: type,
        lignes: lignes.filter((l) => l.designation.trim()).map((l) => ({ designation: l.designation.trim(), quantite: Number(l.quantite) || 1, prix_unitaire: Number(l.prix_unitaire) || 0 })),
      });
      toast.succes(espace === "plateforme" ? `Facture ${data.numero} créée`
        : `${type === "FAC" ? "Facture (brouillon)" : `Proforma ${data.numero}`} créée dans « Factures & proformas »`);
      onFacture?.();
      onFermer();
    } catch (err) { toast.erreur(messageErreur(err, "Facturation impossible")); }
    finally { setOccupe(false); }
  };

  return (
    <Modal ouvert titre={`Facturer la fiche ${fiche.numero}`} onFermer={onFermer}>
      <div className="space-y-3 text-sm">
        {espace === "boutique" ? (
          <div className="flex gap-4">
            <label className="flex items-center gap-1"><input type="radio" checked={type === "FAC"} onChange={() => setType("FAC")} /> Facture</label>
            <label className="flex items-center gap-1"><input type="radio" checked={type === "PRO"} onChange={() => setType("PRO")} /> Proforma</label>
          </div>
        ) : <p className="text-xs text-gray-500">Facture adLyn adressée à la boutique cliente, imprimable depuis la fiche.</p>}
        <p className="rounded bg-gray-50 p-2">Diagnostic — {fiche.type_materiel} : <b>{prix(fiche.prix_diagnostic)}</b></p>
        {lignes.map((l, i) => (
          <div key={i} className="flex gap-1">
            <input className="input" placeholder="Libellé (pièce, main-d'œuvre…)" value={l.designation} onChange={(e) => majLigne(i, "designation", e.target.value)} />
            <input className="input w-16" type="number" min={1} value={l.quantite} onChange={(e) => majLigne(i, "quantite", e.target.value)} aria-label="Quantité" />
            <input className="input w-28" type="number" min={0} placeholder="Prix" value={l.prix_unitaire} onChange={(e) => majLigne(i, "prix_unitaire", e.target.value)} aria-label="Prix unitaire" />
            <button type="button" onClick={() => setLignes(lignes.filter((_, k) => k !== i))} className="px-1 text-red-500" title="Retirer">🗑</button>
          </div>
        ))}
        <button type="button" onClick={() => setLignes([...lignes, { designation: "", quantite: 1, prix_unitaire: "" }])} className="text-xs font-semibold text-primary hover:underline">＋ Ajouter une ligne</button>
        <p className="text-right font-semibold">Total : {prix(total)}</p>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-outline" onClick={onFermer}>Annuler</button>
          <button type="button" className="btn-primary" onClick={valider} disabled={occupe || total <= 0}>{occupe ? "Création…" : "Créer"}</button>
        </div>
      </div>
    </Modal>
  );
}

// ---- Barre d'actions de la fiche -----------------------------------------------------------
export default function MaintenanceActions({ fiche, espace, services, onChange }) {
  const toast = useToast();
  const base = baseApi(espace);
  const [envoiWa, setEnvoiWa] = useState(false);
  const [facturer, setFacturer] = useState(false);
  const [montantLien, setMontantLien] = useState("");
  const [occupe, setOccupe] = useState(false);
  const lien = fiche.lien_paiement;
  const facture = fiche.facture;

  // Lien de paiement : montant du diagnostic, ou montant saisi
  const creerLien = async () => {
    setOccupe(true);
    try {
      await apiClient.post(`${base}/${fiche.id}/lien-paiement`, { montant: Number(montantLien) || null });
      toast.succes("Lien de paiement créé");
      setMontantLien("");
      onChange();
    } catch (err) { toast.erreur(messageErreur(err, "Lien de paiement impossible")); }
    finally { setOccupe(false); }
  };
  const copier = async () => {
    try { await navigator.clipboard.writeText(lien.url); toast.succes("Lien copié"); }
    catch { window.prompt("Copiez le lien :", lien.url); }
  };

  return (
    <div className="space-y-3 rounded-xl bg-gray-50 p-3">
      <Photos fiche={fiche} base={base} onChange={onChange} />

      <div className="flex flex-wrap items-center gap-2">
        {/* WhatsApp */}
        <button type="button" className="btn-primary btn-sm bg-emerald-600 hover:bg-emerald-700" disabled={!services.whatsapp}
          title={services.whatsapp ? "" : "WhatsApp n'est pas encore branché sur la plateforme"} onClick={() => setEnvoiWa(true)}>
          💬 Envoyer par WhatsApp
        </button>

        {/* Lien de paiement Mobile Money */}
        {lien ? (
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-white px-2 py-1 text-xs ring-1 ring-gray-200">
            💳 {prix(lien.montant)}
            <span className={`badge ${lien.paye ? "bg-emerald-100 text-emerald-700" : lien.statut === "ECHEC" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>
              {lien.paye ? "payé" : lien.statut === "EN_ATTENTE" ? "paiement en cours" : lien.statut === "ECHEC" ? "échec" : "en attente"}
            </span>
            {!lien.paye && <button type="button" className="font-semibold text-primary" onClick={copier}>Copier le lien</button>}
          </span>
        ) : null}
        {!lien?.paye && services.paiement && (
          <span className="inline-flex items-center gap-1">
            <input type="number" min={1} className="input w-28 py-1.5 text-sm" placeholder={String(fiche.prix_diagnostic || "")} value={montantLien}
              onChange={(e) => setMontantLien(e.target.value)} aria-label="Montant du lien de paiement" title="Vide = prix du diagnostic" />
            <button type="button" className="btn-outline btn-sm" onClick={creerLien} disabled={occupe}>
              {lien ? "Nouveau lien" : "Lien de paiement"}
            </button>
          </span>
        )}
        {!services.paiement && !lien && (
          <span className="text-xs text-gray-500">Paiement Mobile Money indisponible{espace === "boutique" ? " (dossier d'identification de la boutique à faire valider)" : ""}.</span>
        )}

        {/* Facture */}
        {facture && (espace === "plateforme" ? (
          <a href={lienImpression(espace, fiche.id, "facture")} target="_blank" rel="noreferrer" className="badge bg-indigo-100 text-indigo-700">🧾 Facture {facture.numero}</a>
        ) : (
          <Link to={`/gestion/documents/${facture.id}`} className="badge bg-indigo-100 text-indigo-700">
            🧾 {facture.type_document === "FAC" ? `Facture ${facture.numero || "(brouillon)"}` : `Proforma ${facture.numero}`}
          </Link>
        ))}
        {services.facturation && (espace === "boutique" ? facture?.type_document !== "FAC" : !facture) && (
          <button type="button" className="btn-outline btn-sm" onClick={() => setFacturer(true)}>🧾 Facturer</button>
        )}
      </div>

      {envoiWa && <EnvoiWhatsApp fiche={fiche} base={base} services={services} onFermer={() => setEnvoiWa(false)} onEnvoye={onChange} />}
      {facturer && <Facturer fiche={fiche} base={base} espace={espace} onFermer={() => setFacturer(false)} onFacture={onChange} />}
    </div>
  );
}
