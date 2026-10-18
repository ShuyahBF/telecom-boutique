# adLyn en application Android (APK) avec PWABuilder

Ce guide est écrit pour un débutant. Le site adLyn est déjà prêt : il ne reste qu'à fabriquer l'application sur le site PWABuilder.

## Ce qu'il faut saisir

| Champ dans PWABuilder | Valeur à utiliser |
|---|---|
| Adresse du site | `https://adlynservice.com` |
| Nom de l'application | `adLyn` |
| Identifiant de package (Package ID) | `com.sawali.adlyn` |

## Les étapes

1. Allez sur **https://www.pwabuilder.com**, collez `https://adlynservice.com`, puis cliquez sur **Start**.
2. PWABuilder analyse le site. Le manifeste, le service worker et les icônes doivent être validés (coches vertes).
3. Cliquez sur **Package for stores**, puis sur **Android**.
4. Saisissez le nom `adLyn` et l'identifiant de package `com.sawali.adlyn`. Laissez les autres choix par défaut, puis cliquez sur **Generate**.
5. **Téléchargez le fichier ZIP** proposé. Il contient l'application (fichiers `.apk` et `.aab`) et la **clé de signature**.
6. **Gardez la clé de signature précieusement** (fichier `.keystore` ou `.jks`, avec ses mots de passe) : sans elle, vous ne pourrez plus jamais mettre à jour l'application. Faites-en une copie hors de votre ordinateur.
7. Ouvrez le fichier `signing-key-info.txt` du ZIP : il contient l'**empreinte SHA-256** de la clé. Donnez **uniquement cette empreinte** (une longue suite de lettres et chiffres séparés par « : ») à Claude. Claude la placera dans le fichier `assetlinks.json` du site, et l'application s'ouvrira alors en plein écran, sans barre d'adresse.
8. Quand Claude vous confirme la mise à jour du site, installez le fichier `.apk` sur un téléphone Android pour essayer. Le fichier `.aab` sert à publier sur le Play Store.

## Important : ne jamais partager

- Ne donnez **jamais** le fichier de clé (`.keystore`, `.jks`) ni les **mots de passe** dans le chat, par e-mail ou dans le dépôt GitHub.
- Seule l'empreinte SHA-256 se partage : elle est publique par nature.

## Ce que fait l'application

- Elle ouvre adLyn en plein écran, avec l'icône adLyn sur l'écran d'accueil.
- Elle charge toujours la dernière version du site : aucune mise à jour de l'application n'est nécessaire quand le site change.
- Sans Internet, elle affiche un écran « Pas de connexion Internet » avec un bouton **Réessayer**.
- Sur le site, le bouton **Installer l'application** (page de connexion) permet aussi d'installer adLyn directement depuis Chrome, sans passer par un fichier APK.
