import { NavLink } from "react-router-dom";

// Onglets communs aux pages « Stock » et « Bons d'entrée » :
// chaque onglet est un lien vers l'autre page.
export default function OngletsStock() {
  const classe = ({ isActive }) =>
    `whitespace-nowrap border-b-2 px-3 py-2 text-sm font-semibold transition ${
      isActive ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-800"}`;
  return (
    <div className="no-print -mx-1 mb-5 flex gap-1 overflow-x-auto border-b border-gray-200 px-1">
      <NavLink to="/gestion/stock" end className={classe}>🏷️ Journal des mouvements</NavLink>
      <NavLink to="/gestion/stock/bons" className={classe}>📥 Bons d'entrée (réceptions)</NavLink>
    </div>
  );
}
