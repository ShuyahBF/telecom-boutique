import MaintenanceEquipements from "@/pages/gestion/MaintenanceEquipements";
import { EnTetePlateforme } from "./_plateforme/composants";

// « Maintenance des équipements » de la PLATEFORME (super-administrateur) :
// matériel confié par les boutiques adLyn (même écran que celui des boutiques,
// les clients proposés étant les boutiques).
export default function MaintenanceEquipementsPlateforme() {
  return (
    <div className="min-h-screen bg-papier">
      <EnTetePlateforme />
      <main className="mx-auto max-w-7xl p-4 sm:p-6">
        <MaintenanceEquipements espace="plateforme" />
      </main>
    </div>
  );
}
