import { createContext, useCallback, useContext, useMemo, useState } from "react";

// Petites notifications en bas de l'écran (« Enregistré », erreurs...).
// Utilisation : const toast = useToast(); toast.succes("Enregistré"); toast.erreur("…")
const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [messages, setMessages] = useState([]);

  const afficher = useCallback((texte, type) => {
    const id = Math.random().toString(36).slice(2);
    setMessages((m) => [...m, { id, texte, type }]);
    setTimeout(() => setMessages((m) => m.filter((x) => x.id !== id)), 4000);
  }, []);

  // useMemo : le même objet est renvoyé à chaque affichage, ce qui permet de
  // l'utiliser sans risque dans les dépendances des useEffect/useCallback
  const api = useMemo(() => ({
    succes: (t) => afficher(t, "succes"),
    erreur: (t) => afficher(t, "erreur"),
    info: (t) => afficher(t, "info"),
  }), [afficher]);

  const couleurs = { succes: "bg-green-600", erreur: "bg-red-600", info: "bg-gray-800" };
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="no-print pointer-events-none fixed inset-x-0 bottom-4 z-[100] flex flex-col items-center gap-2 px-4">
        {messages.map((m) => (
          <div key={m.id} className={`pointer-events-auto animate-slide-up rounded-xl px-4 py-3 text-sm font-medium text-white shadow-lg ${couleurs[m.type]}`}>
            {m.texte}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
