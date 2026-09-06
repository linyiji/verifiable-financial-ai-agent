import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE = "a[href],button:not([disabled]),input:not([disabled]),textarea:not([disabled]),select:not([disabled]),[tabindex]:not([tabindex='-1'])";
const overlayStack: Array<{ id: symbol; element: HTMLElement }> = [];
let originalBodyOverflow = "";

export function OverlaySurface({ kind, titleId, label, className = "", onClose, restoreFocus = true, children, footer }: {
  kind: "modal" | "drawer";
  titleId: string;
  label?: string;
  className?: string;
  onClose: () => void;
  restoreFocus?: boolean;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const surfaceRef = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const overlayId = useRef(Symbol("overlay-surface"));
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const root = document.getElementById("root");
    const surface = surfaceRef.current;
    if (overlayStack.length === 0) {
      originalBodyOverflow = document.body.style.overflow;
      if (root) root.inert = true;
    }
    const previousOverlay = overlayStack.at(-1);
    if (previousOverlay) previousOverlay.element.inert = true;
    if (surface) overlayStack.push({ id: overlayId.current, element: surface });
    document.body.style.overflow = "hidden";
    const focusables = () => [...(surface?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])];
    window.requestAnimationFrame(() => (surface?.querySelector<HTMLElement>("[data-autofocus]") ?? focusables()[0] ?? surface)?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (overlayStack.at(-1)?.id !== overlayId.current) return;
      if (event.key === "Escape") { event.preventDefault(); onCloseRef.current(); return; }
      if (event.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) { event.preventDefault(); surface?.focus(); return; }
      const first = items[0];
      const last = items.at(-1)!;
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      const index = overlayStack.findIndex((entry) => entry.id === overlayId.current);
      if (index >= 0) overlayStack.splice(index, 1);
      const nextTop = overlayStack.at(-1);
      if (nextTop) nextTop.element.inert = false;
      if (overlayStack.length === 0) {
        if (root) root.inert = false;
        document.body.style.overflow = originalBodyOverflow;
      }
      if (restoreFocus) window.requestAnimationFrame(() => returnFocus.current?.focus({ preventScroll: true }));
    };
  }, [restoreFocus]);

  return createPortal(
    <div className={`overlay-layer overlay-${kind}`}>
      <div className="overlay-scrim" aria-hidden="true" onMouseDown={(event) => {
        if (event.target === event.currentTarget && overlayStack.at(-1)?.id === overlayId.current) onClose();
      }} />
      <div
        ref={surfaceRef}
        className={`${kind === "drawer" ? "drawer show" : "modal show"} ${className}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-label={label}
        tabIndex={-1}
      >
        {children}
        {footer && <div className={`${kind === "drawer" ? "drawer" : "modal"}-foot`}>{footer}</div>}
      </div>
    </div>,
    document.body
  );
}
