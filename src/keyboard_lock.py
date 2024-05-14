import json
import threading
import time
import tkinter as tk
import webbrowser
from queue import Queue
import plyer

from pynput import keyboard
from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

DEFAULT_HOTKEY = "ctrl+shift+l"
CONFIG_FILE = "config.json"


def open_about():
    webbrowser.open("https://github.com/richiehowelll/CatLock", new=2)


class KeyboardLock:
    def __init__(self):
        self.blocked_keys = set()
        self.program_running = True
        self.listen_for_hotkey = True
        self.hotkey_lock = threading.Lock()
        self.hotkey_thread = None
        self.tray_icon_thread = threading.Thread(target=self.create_tray_icon, daemon=True)
        self.root = None
        self.hotkey = DEFAULT_HOTKEY
        self.opacity = .5
        self.notifications_enabled = True
        self.load_config()
        self.show_overlay_queue = Queue()
        self.show_change_hotkey_queue = Queue()
        self.start_hotkey_listener_thread()
        self.tray_icon_thread.start()

    def load_config(self):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.hotkey = config.get("hotkey", DEFAULT_HOTKEY)
                self.opacity = config.get("opacity", 0.5)
                self.notifications_enabled = config.get("notificationsEnabled", True)
        except (FileNotFoundError, json.JSONDecodeError):
            pass  # Fall back to the default hotkey

    def save_config(self):
        with open(CONFIG_FILE, "w") as f:
            config = {
                "hotkey": self.hotkey,
                "opacity": self.opacity,
                "notificationsEnabled": self.notifications_enabled,
            }
            json.dump(config, f)

    def send_lock_notification(self):
        if self.notifications_enabled:
            plyer.notification.notify(
                app_name="CatLock",
                title="Keyboard Locked",
                message="Click on screen to unlock",
                app_icon="../resources/img/icon.ico",
                timeout=3,
            )
            time.sleep(.1)

    def send_notification_in_thread(self):
        if self.notifications_enabled:
            notification_thread = threading.Thread(target=self.send_lock_notification, daemon=True)
            notification_thread.start()
            notification_thread.join()

    def set_opacity(self, opacity):
        self.opacity = opacity
        self.save_config()

    def set_hotkey(self, new_hotkey):
        self.hotkey = new_hotkey
        self.save_config()

    def toggle_notifications(self):
        self.notifications_enabled = not self.notifications_enabled
        self.save_config()

    def change_hotkey(self):
        self.listen_for_hotkey = False
        if self.hotkey_thread.is_alive():
            self.hotkey_thread.join()

        with self.hotkey_lock:
            hotkey_window = tk.Tk()
            hotkey_window.title("Set Hotkey")
            hotkey_window.geometry("300x150")
            hotkey_window.attributes('-topmost', True)

            hotkey_set = False  # Flag to indicate if hotkey has been set
            entered_keys = []  # List to store the entered keys

            def on_closing():
                nonlocal hotkey_set
                hotkey_window.destroy()
                if not hotkey_set:
                    hotkey_listener.stop()  # Stop the listener if hotkey is not set
                self.start_hotkey_listener_thread()

            def on_key_press(key):
                nonlocal entered_keys
                entered_keys.append(keyboard.from_char(key))
                update_hotkey_entry()

            def update_hotkey_entry():
                hotkey_entry.config(state='normal')
                hotkey_entry.delete(0, 'end')
                hotkey_entry.insert(tk.END, '+'.join(entered_keys))
                hotkey_entry.config(state='readonly')

            def confirm_hotkey():
                nonlocal hotkey_set
                hotkey_set = True
                self.set_hotkey('+'.join(entered_keys))
                print(f"Key Unlocked {self.hotkey}")
                print(f"Hotkey changed to: {self.hotkey}")
                on_closing()

            def cancel_hotkey():
                on_closing()

            hotkey_window.protocol("WM_DELETE_WINDOW", on_closing)

            label = tk.Label(hotkey_window, text="Press keys for hotkey:")
            label.pack(pady=10)

            hotkey_entry = tk.Entry(hotkey_window, width=20)
            hotkey_entry.config(state='readonly')
            hotkey_entry.pack(pady=10)

            confirm_button = tk.Button(hotkey_window, text="Confirm", command=confirm_hotkey)
            confirm_button.pack(pady=5)

            cancel_button = tk.Button(hotkey_window, text="Cancel", command=cancel_hotkey)
            cancel_button.pack(pady=5)

            # Initialize the hotkey listener
            hotkey_listener = keyboard.Listener(on_press=on_key_press, suppress=True)
            hotkey_listener.start()

        hotkey_window.mainloop()

    def lock_keyboard(self):
        self.blocked_keys.clear()
        controller = keyboard.Controller()
        # Simulate pressing an invalid key for each key code in the range
        # for i in range(150):
        #     try:
        #         key = keyboard.KeyCode.from_vk(i)
        #         if key:
        #             controller.press(key)
        #             controller.release(key)
        #             self.blocked_keys.add(i)
        #     except Exception as e:
        #         print(f"Error occurred while simulating key press: {e}")
        self.send_notification_in_thread()

    def unlock_keyboard(self, event=None):
        controller = keyboard.Controller()
        keys = self.hotkey.split('+')
        for key in keys:
            key = key.strip().lower()
            if key.startswith('<') and key.endswith('>'):
                key = key[1:-1]  # Remove angle brackets
                if key == 'ctrl':
                    controller.release(keyboard.Key.ctrl)
                elif key == 'shift':
                    controller.release(keyboard.Key.shift)
                elif key == 'alt':
                    controller.release(keyboard.Key.alt)
            else:
                controller.release(keyboard.KeyCode.from_char(key))
        print(f"Keyboard Unlocked {self.hotkey}")
        if self.root:
            self.root.destroy()

    def show_overlay(self):
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', self.opacity)
        self.root.bind('<Button-1>', self.unlock_keyboard)

        self.lock_keyboard()
        self.root.mainloop()

    def send_hotkey_signal(self):
        self.show_overlay_queue.put(True)

    def send_change_hotkey_signal(self):
        self.show_change_hotkey_queue.put(True)

    def start_hotkey_listener_thread(self):
        with self.hotkey_lock:
            self.listen_for_hotkey = True
            if self.hotkey_thread and threading.current_thread() is not self.hotkey_thread and self.hotkey_thread.is_alive():
                self.hotkey_thread.join()
            self.hotkey_thread = threading.Thread(target=self.hotkey_listener, daemon=True)
            self.hotkey_thread.start()

    def hotkey_listener(self):
        with keyboard.GlobalHotKeys({self.hotkey: self.send_hotkey_signal}) as h:
            while not self.listen_for_hotkey:
                h.stop()
                h.join()

    def create_tray_icon(self):
        image = Image.open("../resources/img/icon.png")
        draw = ImageDraw.Draw(image)
        draw.rectangle((16, 16, 48, 48), fill="white")
        menu = Menu(
            MenuItem("About", open_about),
            MenuItem("Change Hotkey", self.send_change_hotkey_signal),
            MenuItem(
                "Enable/Disable Notifications",
                self.toggle_notifications,
                checked=lambda item: self.notifications_enabled,
            ),
            MenuItem("Set Opacity", Menu(
                MenuItem("5%", lambda: self.set_opacity(0.05)),
                MenuItem("10%", lambda: self.set_opacity(0.1)),
                MenuItem("30%", lambda: self.set_opacity(0.3)),
                MenuItem("50%", lambda: self.set_opacity(0.5)),
                MenuItem("70%", lambda: self.set_opacity(0.7)),
                MenuItem("90%", lambda: self.set_opacity(0.9)),
            )),
            MenuItem("Quit", self.quit_program),
        )
        tray_icon = Icon("Keyboard Locker", image, "Keyboard Locker", menu)
        tray_icon.run()

    def quit_program(self, icon, item):
        self.program_running = False
        self.unlock_keyboard()
        icon.stop()
        print("Program Exiting")

    def start(self):
        print("Program Starting")
        while self.program_running:
            if not self.show_overlay_queue.empty():
                self.show_overlay_queue.get(block=False)
                self.show_overlay()
            elif not self.show_change_hotkey_queue.empty():
                self.show_change_hotkey_queue.get(block=False)
                self.change_hotkey()
            time.sleep(.1)
