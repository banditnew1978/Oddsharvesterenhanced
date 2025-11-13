import tkinter as tk
from tkinter import scrolledtext, messagebox
import re

def parse_log():
    log_text = text_area.get("1.0", tk.END).strip()
    if not log_text:
        messagebox.showwarning("Uyarı", "Lütfen log metnini yapıştırın.")
        return

    # Her sezon bloğunu bulmak için başlangıç noktası: "Capturing links for ... season=XXXX-XXXX"
    season_blocks = re.split(r"(?=Capturing links for.*season=\d{4}-\d{4})", log_text)

    results = []

    for block in season_blocks:
        # Sezonu çıkar
        season_match = re.search(r"season=(\d{4}-\d{4})", block)
        if not season_match:
            continue
        season = season_match.group(1)

        # Pagination sayısını bul (örn: "Found 9 pagination links")
        pag_match = re.search(r"Found (\d+) pagination links", block)
        pagination_pages = int(pag_match.group(1)) if pag_match else 0

        # Toplam link sayısını bul (örn: "Total links found: 380")
        link_match = re.search(r"Total links found: (\d+)", block)
        total_links = int(link_match.group(1)) if link_match else 0

        results.append({
            "season": season,
            "pagination_pages": pagination_pages,
            "total_links": total_links
        })

    # Sonuçları formatla
    output = ""
    for res in results:
        output += f"Sezon: {res['season']} → Pagination Sayfası: {res['pagination_pages']}, Toplam Link: {res['total_links']}\n"

    if output:
        result_text.config(state='normal')
        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, output.strip())
        result_text.config(state='disabled')
    else:
        messagebox.showinfo("Bilgi", "Hiçbir sezon verisi bulunamadı.")

# GUI Ayarları
root = tk.Tk()
root.title("OddsPortal Log Parser")
root.geometry("800x600")

tk.Label(root, text="Log metnini aşağıya yapıştırın:", font=("Arial", 12)).pack(pady=5)

text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=90, height=15)
text_area.pack(padx=10, pady=5)

tk.Button(root, text="Analiz Et", command=parse_log, font=("Arial", 12), bg="#4CAF50", fg="white").pack(pady=10)

tk.Label(root, text="Sonuçlar:", font=("Arial", 12)).pack(pady=5)

result_text = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=90, height=10, state='disabled')
result_text.pack(padx=10, pady=5)

root.mainloop()