import { Navigate, useLocation } from "react-router-dom";
import { aLeRole, peut, useAuth } from "@/context/AuthContext";
import { optionActive } from "@/lib/options";
import Chargement from "@/components/Chargement";

// Réserve une page au personnel connecté, et éventuellement à une permission
// (ex. permission="facturation") ou à certains rôles (ex. roles={["super_admin"]}),
// et à une option de la barre latérale activée pour la boutique (ex. option="clients",
// ou une liste : il suffit que l'une soit active). Option désactivée = retour au
// tableau de bord (cas d'une adresse tapée à la main).
export default function RouteProtegee({ roles, permission, option, children }) {
  const { user, boutique, chargement } = useAuth();
  const location = useLocation();
  if (chargement) return <Chargement plein />;
  if (!user) return <Navigate to="/connexion" replace state={{ depuis: location.pathname }} />;
  // Mot de passe provisoire (reçu par e-mail/SMS ou donné par le DG) : à changer d'abord
  if (user.doit_changer_mot_de_passe) return <Navigate to="/mot-de-passe" replace state={{ depuis: location.pathname }} />;
  if (option && boutique && !optionActive(boutique, option)) return <Navigate to="/gestion" replace />;
  if ((roles && !aLeRole(user, ...roles)) || (permission && !peut(user, permission))) {
    return <div className="p-10 text-center text-gray-600">Cette page n'est pas accessible avec votre rôle.</div>;
  }
  return children;
}
