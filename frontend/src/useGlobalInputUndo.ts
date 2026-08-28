import { useEffect } from "react";

type TextControl = HTMLInputElement | HTMLTextAreaElement;
type History = {
  current: string;
  undo: string[];
  redo: string[];
  lastInputAt: number;
};

const GROUP_WINDOW_MS = 700;

function isTextControl(target: EventTarget | null): target is TextControl {
  if (target instanceof HTMLTextAreaElement) return true;
  if (!(target instanceof HTMLInputElement)) return false;
  return ["", "text", "email", "password", "search", "tel", "url", "number"].includes(target.type);
}

/**
 * Keeps Ctrl+Z/Ctrl+Y reliable for React-controlled text fields, including
 * fields whose parent rerenders while a workflow is being polled.
 */
export function useGlobalInputUndo(): void {
  useEffect(() => {
    const histories = new WeakMap<TextControl, History>();
    let applyingHistory = false;

    const historyFor = (control: TextControl): History => {
      const existing = histories.get(control);
      if (existing) return existing;
      const created = { current: control.value, undo: [], redo: [], lastInputAt: 0 };
      histories.set(control, created);
      return created;
    };

    const handleFocus = (event: FocusEvent) => {
      if (isTextControl(event.target)) historyFor(event.target);
    };

    const handleInput = (event: Event) => {
      if (!isTextControl(event.target)) return;
      const control = event.target;
      const history = historyFor(control);
      if (applyingHistory) {
        history.current = control.value;
        return;
      }
      if (control.value === history.current) return;
      const now = Date.now();
      if (!history.undo.length || now - history.lastInputAt > GROUP_WINDOW_MS) {
        history.undo.push(history.current);
        if (history.undo.length > 100) history.undo.shift();
      }
      history.current = control.value;
      history.redo = [];
      history.lastInputAt = now;
    };

    const applyValue = (control: TextControl, value: string) => {
      applyingHistory = true;
      const prototype = control instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
      const nativeSetter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
      if (nativeSetter) nativeSetter.call(control, value);
      else control.value = value;
      control.dispatchEvent(new Event("input", { bubbles: true }));
      applyingHistory = false;
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isTextControl(event.target) || !(event.ctrlKey || event.metaKey)) return;
      const undo = event.key.toLowerCase() === "z" && !event.shiftKey;
      const redo = event.key.toLowerCase() === "y" || (event.key.toLowerCase() === "z" && event.shiftKey);
      if (!undo && !redo) return;
      const control = event.target;
      const history = historyFor(control);
      const source = undo ? history.undo : history.redo;
      const target = undo ? history.redo : history.undo;
      const value = source.pop();
      if (value === undefined) return;
      event.preventDefault();
      target.push(history.current);
      history.current = value;
      history.lastInputAt = 0;
      applyValue(control, value);
    };

    document.addEventListener("focusin", handleFocus);
    document.addEventListener("input", handleInput, true);
    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("focusin", handleFocus);
      document.removeEventListener("input", handleInput, true);
      document.removeEventListener("keydown", handleKeyDown, true);
    };
  }, []);
}
