"""GUI básica; worker não acessa Tk e só devolve resultados pela fila."""
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from .model import DeviceConfig
from .builder import build, build_and_flash
from .devices import detect


class App:
    def __init__(self, root):
        self.root = root
        root.title('Estação Rádio — Configurador')
        self.results = queue.Queue()
        self.busy = False
        self.devices = []
        self.role = tk.StringVar(value='estacao')
        self.group = tk.StringVar(value='42')
        self.station_id = tk.StringVar(value='QUARTO')
        self.name = tk.StringVar(value='Quarto')
        self.status = tk.StringVar(value='Escolha o papel e a rede. Feche o gateway antes de gravar.')
        panel = ttk.Frame(root, padding=18)
        panel.pack(fill='both', expand=True)
        self.panel = panel
        roles = ttk.Frame(panel)
        roles.pack(fill='x')
        for role, label in [('central','CENTRAL'),('estacao','ESTAÇÃO'),('ponte','PONTE')]:
            ttk.Radiobutton(roles, text=label, variable=self.role, value=role, command=self.fields).pack(side='left', padx=8)
        self.station = ttk.Frame(panel)
        self.entry(self.station, 'ID (único na rede)', self.station_id)
        self.entry(self.station, 'Nome amigável', self.name)
        self.station.pack(fill='x', pady=8)
        self.entry(panel, 'Rede (0–255; igual em todos os aparelhos da rede)', self.group)
        ttk.Label(panel, text='Uma Central por rede. TTL, som e ACK permanecem nos padrões.').pack(anchor='w', pady=8)
        self.device_box = ttk.Combobox(panel, state='readonly', width=65)
        self.device_box.pack(fill='x')
        self.refresh_button = ttk.Button(panel, text='Atualizar micro:bits USB', command=self.refresh)
        self.refresh_button.pack(anchor='w', pady=5)
        self.generate_button = ttk.Button(panel, text='Gerar firmware .HEX', command=lambda:self.start(False))
        self.generate_button.pack(fill='x', pady=4)
        self.flash_button = ttk.Button(panel, text='Gerar e gravar no micro:bit', command=lambda:self.start(True))
        self.flash_button.pack(fill='x', pady=4)
        ttk.Label(panel, textvariable=self.status, wraplength=550).pack(fill='x', pady=10)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        root.after(100, self.poll)

    @staticmethod
    def entry(parent, label, variable):
        row = ttk.Frame(parent)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text=label).pack(anchor='w')
        ttk.Entry(row, textvariable=variable).pack(fill='x')

    def fields(self):
        if self.role.get() == 'estacao':
            self.station.pack(fill='x', pady=8, after=self.panel.winfo_children()[0])
        else:
            self.station.pack_forget()

    def refresh(self):
        if self.busy:
            return
        self.devices = detect()
        self.device_box['values'] = [d.label for d in self.devices]
        self.device_box.set('')
        if len(self.devices) == 1:
            self.device_box.current(0)
        self.status.set('Nenhum micro:bit V2 identificado. Gerar HEX continua disponível.' if not self.devices else
                        'Selecione o micro:bit desejado.' if len(self.devices)>1 else 'Micro:bit V2 identificado.')

    def start(self, should_flash):
        if self.busy:
            return
        try:
            try:
                group = int(self.group.get())
            except ValueError:
                raise ValueError('Rede deve ser um número inteiro entre 0 e 255.') from None
            config = DeviceConfig(self.role.get(), group, self.station_id.get(), self.name.get()).validated()
            selected = None
            if should_flash:
                index = self.device_box.current()
                if index < 0 or index >= len(self.devices):
                    raise ValueError('Selecione explicitamente um micro:bit identificado na lista.')
                selected = self.devices[index]
                if not messagebox.askyesno('Confirmar gravação', f'Substituir o programa de {selected.label}?\nPapel: {config.role}; rede: {config.group}.\nFeche o gateway antes de continuar.'):
                    return
            else:
                filename = filedialog.asksaveasfilename(title='Salvar HEX no computador', initialfile=config.filename,
                                                   defaultextension='.hex', filetypes=[('Firmware HEX','*.hex')])
                if not filename:
                    return
                destination = Path(filename)
                if destination.exists():
                    raise FileExistsError('Arquivo já existe. Escolha outro nome; não será sobrescrito.')
        except (ValueError, OSError) as e:
            messagebox.showerror('Configuração', str(e))
            return
        self.busy = True
        for button in (self.generate_button, self.flash_button, self.refresh_button):
            button.state(['disabled'])
        self.status.set('Compilando com MakeCode… pode levar alguns minutos. Não desconecte durante a gravação.')
        def work():
            try:
                if selected:
                    message = build_and_flash(config, selected)
                else:
                    result = build(config, destination)
                    message = f'HEX salvo: {result}'
                self.results.put((True, message))
            except Exception as e:
                self.results.put((False, str(e)))
        threading.Thread(target=work, daemon=False).start()

    def poll(self):
        try:
            ok, message = self.results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy = False
            for button in (self.generate_button, self.flash_button, self.refresh_button):
                button.state(['!disabled'])
            self.status.set(message)
            (messagebox.showinfo if ok else messagebox.showerror)('Configurador', message)
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo('Operação em andamento', 'Aguarde concluir para fechar. Não interrompa a gravação USB.')
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
