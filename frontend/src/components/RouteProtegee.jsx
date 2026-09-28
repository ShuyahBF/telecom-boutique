import { Navigate, useLocation } from "react-router-dom";
import { aLeRole, peut, useAuth } from "@/context/AuthContext";
import Chargement from "@/components/Chargement";

// Réserve une page au personnel connecté, et éventuellement à une permission
// (ex. permission="facturation") ou à certains rôles (ex. roles={["super_admin"]}).
export default function RouteProtegee({ roles, permission, children }) {
  const { user, chargement } = useAuth();
  const location = useLocation();
  if (chargement) return <Chargement plein />;
  if (!user) return <Navigate to="/connexion" replace state={{ depuis: location.pathname }} />;
  if ((roles && !aLeRole(user, ...roles)) || (permission && !peut(user, permission))) {
    return <div className="p-10 text-center text-gray-600">Cette page n'est pas accessible avec votre rôle.</div>;
  }
  return children;
}
