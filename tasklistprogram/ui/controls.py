# controls.py
from tkinter import ttk
import tkinter as tk


class AutoCompleteEntry(ttk.Entry):
    def __init__(self, master, get_candidates, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.get_candidates = get_candidates
        self.var = kwargs.get("textvariable") or tk.StringVar()
        self.config(textvariable=self.var)
        self.listbox = None
        self.bind("<KeyRelease>", self._on_key)
        self.bind("<Return>", self._accept)
        self.bind("<Tab>", lambda e: None)
        self.bind("<Down>", self._move_down)
        self.bind("<Up>", self._move_up)
        self.bind("<Escape>", self._hide_list)

    def _on_key(self, event):
        text = self.var.get().strip()
        if not text:
            self._hide_list(event); return
        cands = [c for c in self.get_candidates() if c.lower().startswith(text.lower())]
        if not cands:
            self._hide_list(event); return
        if not self.listbox:
            self.listbox = tk.Listbox(self.master, height=min(6, len(cands)))
            self.listbox.bind("<Return>", self._accept)
            self.listbox.bind("<Double-Button-1>", self._accept)
            self.listbox.bind("<Escape>", self._hide_list)
        else:
            self.listbox.delete(0, tk.END)
        self.listbox.delete(0, tk.END)
        for c in cands:
            self.listbox.insert(tk.END, c)
        x = self.winfo_x()
        y = self.winfo_y() + self.winfo_height()
        self.listbox.place(x=x, y=y, width=self.winfo_width())
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(0)

    def _accept(self, event=None):
        if self.listbox and self.listbox.size() > 0:
            sel = self.listbox.curselection()
            if sel:
                self.var.set(self.listbox.get(sel[0]))
        self._hide_list()
        self.event_generate("<Tab>")
        return "break"

    def _hide_list(self, event=None):
        if self.listbox:
            self.listbox.destroy()
            self.listbox = None

    def _move_down(self, event):
        if not self.listbox: return
        sel = self.listbox.curselection()
        if not sel:
            self.listbox.selection_set(0)
        else:
            i = min(sel[0]+1, self.listbox.size()-1)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(i)
        return "break"

    def _move_up(self, event):
        if not self.listbox: return
        sel = self.listbox.curselection()
        if not sel:
            self.listbox.selection_set(0)
        else:
            i = max(sel[0]-1, 0)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(i)
        return "break"