"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { Toast } from "@vibe/core";

import styles from "./ToastProvider.module.css";

type ToastKind = "normal" | "positive" | "negative";

interface ToastApi {
  show: (message: string, kind?: ToastKind) => void;
}

const ToastContext = createContext<ToastApi>({ show: () => {} });

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<{ message: string; kind: ToastKind; key: number } | null>(null);
  const show = useCallback((message: string, kind: ToastKind = "normal") => {
    setToast({ message, kind, key: Date.now() });
  }, []);
  const api = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div aria-live="polite">
        {toast && (
          <Toast
            key={toast.key}
            open
            className={styles.toast}
            type={toast.kind}
            autoHideDuration={toast.kind === "negative" ? 8000 : 4000}
            onClose={() => setToast(null)}
            closeButtonAriaLabel="Fermer"
          >
            {toast.message}
          </Toast>
        )}
      </div>
    </ToastContext.Provider>
  );
}
