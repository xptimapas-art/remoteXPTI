import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import './Doors.css';
export function AccessDialog({ title, onClose, busy = false, children, footer }: {
  title: string; onClose: () => void; busy?: boolean; children: ReactNode; footer?: ReactNode;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return createPortal(
    <dialog ref={dialog} className="xpti-access xa-dialog" aria-label={title}
      onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
      <header className="xa-dialog-header"><h2>{title}</h2>
        <button type="button" className="xa-icon" aria-label="Fechar" disabled={busy} onClick={onClose}><X /></button>
      </header>
      <div className="xa-dialog-body">{children}</div>
      {footer && <footer className="xa-dialog-footer">{footer}</footer>}
    </dialog>, document.body,
  );
}
