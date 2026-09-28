import { classeStatut, libelleStatut } from "@/lib/statuts";

// Pastille colorée de statut. Exemple : <Badge table={STATUTS_SAV} statut="PRET" />
export default function Badge({ table, statut, children, className = "" }) {
  if (children) return <span className={`badge ${className}`}>{children}</span>;
  return <span className={`badge ${classeStatut(table, statut)} ${className}`}>{libelleStatut(table, statut)}</span>;
}
