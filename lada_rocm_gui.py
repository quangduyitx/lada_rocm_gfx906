#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lada ROCm Studio (CustomTkinter GUI)
Phần mềm phục hồi video AI Mosaic (BasicVSR++) tối ưu cho GPU AMD Radeon Pro VII (Vega 20 / GFX906 32GB VRAM)
Chạy trên nền tảng ROCm 7.14 (TheRock build) và PyTorch 2.13.0+gfx906.
"""

import sys
import os

_script_dir = os.path.dirname(os.path.abspath(__file__))
while _script_dir in sys.path:
    sys.path.remove(_script_dir)
if sys.path and sys.path[0] == "":
    sys.path.pop(0)

import subprocess
import json
import time
import re
import threading
import queue
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

SCRIPT_DIR = Path(__file__).resolve().parent
VENV_PYTHON = SCRIPT_DIR / ".venv" / "bin" / "python3"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)
LADA_CLI_CMD = [str(VENV_PYTHON), "-m", "lada.cli.main"]
MODEL_WEIGHTS_DIR = SCRIPT_DIR / "model_weights"
ICON_FILE = SCRIPT_DIR / "assets" / "io.github.ladaapp.lada.png"

SUPPORTED_EXTS = {".mp4", ".mkv", ".mov", ".avi", ".wmv", ".webm", ".ts"}

FONT_UI = "Noto Sans"
FONT_MONO = "Noto Sans Mono"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
ctk.ThemeManager.theme["CTkFont"]["family"] = FONT_UI
ctk.ThemeManager.theme["CTkFont"]["size"] = 13


def ui_font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT_UI, size=size, weight=weight)


def mono_font(size=11, weight="normal"):
    return ctk.CTkFont(family=FONT_MONO, size=size, weight=weight)


class LadaRocmApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Lada ROCm Studio — AMD Radeon Pro VII (Vega 20 32GB)")
        self.geometry("1120x840")
        self.minsize(1020, 720)

        if ICON_FILE.exists():
            try:
                img = tk.PhotoImage(file=str(ICON_FILE))
                self.iconphoto(True, img)
            except Exception:
                pass

        self.current_worker = None
        self.stop_requested = False
        self.active_proc = None

        self._build_header()
        self._build_tabs()
        self._build_status_bar()

        # Telemetry cập nhật mỗi 3s
        self._update_gpu_telemetry()

    def _build_header(self):
        header_frame = ctk.CTkFrame(self, corner_radius=10)
        header_frame.pack(fill="x", padx=15, pady=(12, 8))

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=15, pady=8)

        title_lbl = ctk.CTkLabel(
            title_box,
            text="⚡ LADA ROCM STUDIO",
            font=ui_font(21, "bold"),
            text_color="#f43f5e"
        )
        title_lbl.pack(anchor="w")

        sub_lbl = ctk.CTkLabel(
            title_box,
            text="Phục hồi video Mosaic BasicVSR++ trên AMD Radeon Pro VII (Vega 20 / GFX906 32GB)",
            font=ui_font(12),
            text_color="#94a3b8"
        )
        sub_lbl.pack(anchor="w")

        self.gpu_telemetry_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.gpu_telemetry_frame.pack(side="right", padx=15, pady=5)

        self.gpu_badge = ctk.CTkLabel(
            self.gpu_telemetry_frame,
            text="AMD Vega 20: Đang đọc...",
            font=ui_font(12, "bold"),
            fg_color="#1e293b",
            corner_radius=6,
            padx=12,
            pady=6,
            text_color="#cbd5e1"
        )
        self.gpu_badge.pack(anchor="e")

    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self, corner_radius=10)
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 8))

        self.tab_main = self.tabview.add("🎬 Xử lý Video (ROCm)")
        self.tab_hw = self.tabview.add("⚙️ Thông số GPU & ROCm")
        self.tab_diag = self.tabview.add("📊 Kiểm tra Hệ thống")

        self._build_main_tab()
        self._build_hw_tab()
        self._build_diag_tab()

    def _build_main_tab(self):
        parent = self.tab_main

        # 1. Khung chọn Tệp / Thư mục
        file_frame = ctk.CTkFrame(parent, corner_radius=8)
        file_frame.pack(fill="x", padx=10, pady=8)

        # Video đầu vào
        ctk.CTkLabel(file_frame, text="Video Đầu vào:", font=ui_font(12, "bold")).grid(
            row=0, column=0, padx=10, pady=6, sticky="w"
        )
        self.entry_input = ctk.CTkEntry(
            file_frame, placeholder_text="Chọn tệp video hoặc thư mục chứa video...", width=600
        )
        self.entry_input.grid(row=0, column=1, padx=5, pady=6, sticky="ew")

        btn_box = ctk.CTkFrame(file_frame, fg_color="transparent")
        btn_box.grid(row=0, column=2, padx=10, pady=6)

        ctk.CTkButton(
            btn_box, text="Chọn Tệp...", width=95, command=self._browse_file
        ).pack(side="left", padx=3)
        ctk.CTkButton(
            btn_box, text="Chọn Thư mục...", width=105, command=self._browse_dir
        ).pack(side="left", padx=3)

        # Thư mục đích
        ctk.CTkLabel(file_frame, text="Thư mục Đích:", font=ui_font(12, "bold")).grid(
            row=1, column=0, padx=10, pady=6, sticky="w"
        )
        self.entry_output = ctk.CTkEntry(
            file_frame, placeholder_text="Để trống để lưu cùng thư mục nguồn...", width=600
        )
        self.entry_output.grid(row=1, column=1, padx=5, pady=6, sticky="ew")

        ctk.CTkButton(
            file_frame, text="Chọn Thư mục...", width=105, command=self._browse_output_dir
        ).grid(row=1, column=2, padx=10, pady=6)

        file_frame.columnconfigure(1, weight=1)

        # 2. Khung Tùy chọn Cấu hình Mô hình & Hiệu năng
        opt_frame = ctk.CTkFrame(parent, corner_radius=8)
        opt_frame.pack(fill="x", padx=10, pady=(0, 8))

        # Hàng 0: Models
        ctk.CTkLabel(opt_frame, text="Mô hình Nhận diện (YOLO):", font=ui_font(12)).grid(
            row=0, column=0, padx=10, pady=6, sticky="w"
        )
        self.cmb_det = ctk.CTkComboBox(
            opt_frame, values=["v4-fast", "v4-accurate", "v2"], width=170
        )
        self.cmb_det.set("v4-fast")
        self.cmb_det.grid(row=0, column=1, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(opt_frame, text="Mô hình Phục hồi:", font=ui_font(12)).grid(
            row=0, column=2, padx=15, pady=6, sticky="w"
        )
        self.cmb_rest = ctk.CTkComboBox(
            opt_frame, values=["basicvsrpp-v1.2", "deepmosaics"], width=170
        )
        self.cmb_rest.set("basicvsrpp-v1.2")
        self.cmb_rest.grid(row=0, column=3, padx=8, pady=6, sticky="w")

        # Hàng 1: Encoder & Length
        ctk.CTkLabel(opt_frame, text="Độ dài Clip (Frames):", font=ui_font(12)).grid(
            row=1, column=0, padx=10, pady=6, sticky="w"
        )
        self.cmb_clip_len = ctk.CTkComboBox(
            opt_frame, values=["120", "180", "240", "300"], width=170
        )
        self.cmb_clip_len.set("240")
        self.cmb_clip_len.grid(row=1, column=1, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(opt_frame, text="Mã hóa Video (Encoder):", font=ui_font(12)).grid(
            row=1, column=2, padx=15, pady=6, sticky="w"
        )
        self.cmb_encoder = ctk.CTkComboBox(
            opt_frame,
            values=[
                "hevc-nvidia-gpu-hq (Khuyên dùng: NVENC siêu nhanh)",
                "hevc-nvidia-gpu-balanced (NVENC cân bằng)",
                "h264-nvidia-gpu-fast (NVENC H.264 nhanh)",
                "h264-cpu-fast (CPU x264)",
                "h264-cpu-uhq (CPU x264 siêu nét)",
                "av1-cpu-uhq (CPU SVT-AV1)",
            ],
            width=240
        )
        self.cmb_encoder.set("hevc-nvidia-gpu-hq (Khuyên dùng: NVENC siêu nhanh)")
        self.cmb_encoder.grid(row=1, column=3, padx=8, pady=6, sticky="w")

        # Hàng 2: Checkboxes
        check_box = ctk.CTkFrame(opt_frame, fg_color="transparent")
        check_box.grid(row=2, column=0, columnspan=4, padx=10, pady=6, sticky="w")

        self.var_fp16 = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            check_box, text="Bật FP16 (Tăng tốc độ, tiết kiệm VRAM)", variable=self.var_fp16
        ).pack(side="left", padx=(0, 20))

        self.var_face_ignore = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            check_box, text="Bỏ qua khuôn mặt (Tránh méo mặt)", variable=self.var_face_ignore
        ).pack(side="left", padx=10)

        # 3. Nút Điều khiển
        ctl_frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctl_frame.pack(fill="x", padx=10, pady=5)

        self.btn_start = ctk.CTkButton(
            ctl_frame,
            text="▶ BẮT ĐẦU XỬ LÝ (AMD GPU)",
            font=ui_font(14, "bold"),
            fg_color="#059669",
            hover_color="#10b981",
            height=40,
            command=self._on_start_click
        )
        self.btn_start.pack(side="left", padx=(0, 10), fill="x", expand=True)

        self.btn_stop = ctk.CTkButton(
            ctl_frame,
            text="⏹ DỪNG LẠI",
            font=ui_font(14, "bold"),
            fg_color="#dc2626",
            hover_color="#ef4444",
            height=40,
            state="disabled",
            command=self._on_stop_click
        )
        self.btn_stop.pack(side="left", padx=5)

        self.btn_open_out = ctk.CTkButton(
            ctl_frame,
            text="📂 Mở Thư mục Đích",
            font=ui_font(13),
            height=40,
            command=self._open_output_dir
        )
        self.btn_open_out.pack(side="left", padx=5)

        # 4. Tiến độ & Đo tốc độ it/s
        prog_frame = ctk.CTkFrame(parent, corner_radius=8)
        prog_frame.pack(fill="x", padx=10, pady=8)

        metric_row = ctk.CTkFrame(prog_frame, fg_color="transparent")
        metric_row.pack(fill="x", padx=12, pady=(8, 4))

        self.lbl_speed = ctk.CTkLabel(
            metric_row,
            text="⚡ Tốc độ: 0.0 fps",
            font=ui_font(14, "bold"),
            text_color="#38bdf8"
        )
        self.lbl_speed.pack(side="left")

        self.lbl_eta = ctk.CTkLabel(
            metric_row,
            text="⏱ Còn lại: Đang chờ...",
            font=ui_font(13),
            text_color="#94a3b8"
        )
        self.lbl_eta.pack(side="left", padx=25)

        self.lbl_frames = ctk.CTkLabel(
            metric_row,
            text="Khung hình: 0 / 0 (0%)",
            font=ui_font(13),
            text_color="#cbd5e1"
        )
        self.lbl_frames.pack(side="right")

        self.prog_bar = ctk.CTkProgressBar(prog_frame, height=12)
        self.prog_bar.pack(fill="x", padx=12, pady=(2, 4))
        self.prog_bar.set(0.0)

        sub_metric_row = ctk.CTkFrame(prog_frame, fg_color="transparent")
        sub_metric_row.pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_stage = ctk.CTkLabel(
            sub_metric_row,
            text="📍 Công đoạn: Sẵn sàng",
            font=ui_font(12, "bold"),
            text_color="#34d399"
        )
        self.lbl_stage.pack(side="left")

        self.lbl_elapsed = ctk.CTkLabel(
            sub_metric_row,
            text="Đã chạy: 00:00",
            font=ui_font(12),
            text_color="#94a3b8"
        )
        self.lbl_elapsed.pack(side="right")

        # 5. Nhật ký Kỹ thuật (Technical Logs)
        log_head = ctk.CTkFrame(parent, fg_color="transparent")
        log_head.pack(fill="x", padx=10, pady=(2, 2))

        ctk.CTkLabel(log_head, text="📋 Nhật ký Kỹ thuật (Pipeline Events):", font=ui_font(12, "bold")).pack(side="left")
        ctk.CTkButton(
            log_head, text="Xóa Log", width=70, height=22, font=ui_font(11), command=self._clear_log
        ).pack(side="right")

        self.txt_log = ctk.CTkTextbox(parent, font=mono_font(11), corner_radius=8)
        self.txt_log.pack(fill="both", expand=True, padx=10, pady=(0, 6))

    def _build_hw_tab(self):
        parent = self.tab_hw

        card = ctk.CTkFrame(parent, corner_radius=10)
        card.pack(fill="both", expand=True, padx=15, pady=15)

        ctk.CTkLabel(card, text="Thông số Phần cứng AMD ROCm", font=ui_font(18, "bold"), text_color="#f43f5e").pack(
            anchor="w", padx=20, pady=(15, 5)
        )

        info_text = (
            "• Thiết bị: AMD Radeon Pro VII (Kiến trúc Vega 20 / GFX906)\n"
            "• Dung lượng Bộ nhớ: 32 GB HBM2 (Băng thông cực cao ~1024 GB/s)\n"
            "• Chuẩn giao tiếp: PCIe Gen 3.0 x16 (Băng thông bus ~12.8 GB/s)\n"
            "• Nền tảng ROCm: ROCm 7.14 (TheRock GFX906 Build)\n"
            "• Phiên bản PyTorch: 2.13.0+gfx906 (Tương thích Python 3.12)\n"
            "• Giao diện HIP: torch.cuda.is_available() = True (cuda:0)\n"
            "• Bản vá Deformable Convolution: Tích hợp GPU-native fallback\n\n"
            "Mẹo tối ưu hiệu năng GFX906:\n"
            "1. Undervolt: Dùng phần mềm LACT hạ điện áp P-State cao nhất xuống ~975-1025mV để chống chạm trần 190W.\n"
            "2. Compute Power Profile: Đặt power profile sang Compute mode để giữ xung HBM2 luôn ở mức 1000MHz.\n"
            "3. Nâng trần Max Clip Length: Nhờ có 32GB VRAM, bạn có thể tự tin đặt 240 hoặc 300 frames."
        )
        ctk.CTkLabel(card, text=info_text, font=ui_font(13), justify="left").pack(anchor="w", padx=20, pady=10)

    def _build_diag_tab(self):
        parent = self.tab_diag

        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", padx=15, pady=10)

        ctk.CTkLabel(top, text="Kiểm tra Tính toàn vẹn Môi trường ROCm:", font=ui_font(14, "bold")).pack(side="left")
        ctk.CTkButton(
            top, text="🔍 Chạy Chẩn đoán", font=ui_font(12, "bold"), command=self._run_diagnostic
        ).pack(side="right")

        self.txt_diag = ctk.CTkTextbox(parent, font=mono_font(11), corner_radius=8)
        self.txt_diag.pack(fill="both", expand=True, padx=15, pady=(0, 10))

    def _build_status_bar(self):
        bar = ctk.CTkFrame(self, height=28, corner_radius=0)
        bar.pack(fill="x", side="bottom")

        self.lbl_status = ctk.CTkLabel(bar, text="Sẵn sàng", font=ui_font(11), text_color="#94a3b8")
        self.lbl_status.pack(side="left", padx=15)

        self.lbl_ver = ctk.CTkLabel(bar, text="Lada ROCm v0.11.1 • AMD GFX906", font=ui_font(11), text_color="#64748b")
        self.lbl_ver.pack(side="right", padx=15)

    def _browse_file(self):
        file_path = filedialog.askopenfilename(
            title="Chọn tệp Video cần phục hồi",
            filetypes=[("Video Files", "*.mp4 *.mkv *.mov *.avi *.webm *.ts"), ("All Files", "*.*")]
        )
        if file_path:
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, file_path)

    def _browse_dir(self):
        dir_path = filedialog.askdirectory(title="Chọn Thư mục chứa Video")
        if dir_path:
            self.entry_input.delete(0, "end")
            self.entry_input.insert(0, dir_path)

    def _browse_output_dir(self):
        dir_path = filedialog.askdirectory(title="Chọn Thư mục Lưu kết quả")
        if dir_path:
            self.entry_output.delete(0, "end")
            self.entry_output.insert(0, dir_path)

    def _open_output_dir(self):
        out = self.entry_output.get().strip()
        if not out or not os.path.isdir(out):
            inp = self.entry_input.get().strip()
            if inp:
                out = os.path.dirname(inp) if os.path.isfile(inp) else inp
        if out and os.path.isdir(out):
            subprocess.Popen(["xdg-open", out])
        else:
            messagebox.showinfo("Thông báo", "Chưa xác định được thư mục đích.")

    def _clear_log(self):
        self.txt_log.delete("1.0", "end")

    def log(self, text):
        def _append():
            self.txt_log.insert("end", text + "\n")
            self.txt_log.see("end")
        self.after(0, _append)

    def _update_gpu_telemetry(self):
        def _fetch():
            try:
                out = subprocess.check_output(
                    ["rocm-smi", "--showtemp", "--showuse", "--showpower", "--showmemuse"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=2
                )
                temp = "N/A"
                power = "N/A"
                use = "N/A"
                mem = "N/A"
                for line in out.splitlines():
                    if "Temperature (Sensor edge)" in line:
                        m = re.search(r"(\d+\.?\d*)", line)
                        if m: temp = f"{m.group(1)}°C"
                    elif "Package Power" in line:
                        m = re.search(r"(\d+\.?\d*)", line)
                        if m: power = f"{m.group(1)}W"
                    elif "GPU use" in line:
                        m = re.search(r"(\d+)", line)
                        if m: use = f"{m.group(1)}%"
                    elif "GPU Memory Allocated" in line:
                        m = re.search(r"(\d+)", line)
                        if m: mem = f"{m.group(1)}%"

                badge_text = f"AMD Radeon Pro VII: {temp} • {power} • GPU: {use} • VRAM: {mem} / 32GB"
                self.after(0, lambda: self.gpu_badge.configure(text=badge_text, text_color="#38bdf8"))
            except Exception:
                self.after(0, lambda: self.gpu_badge.configure(text="AMD Radeon Pro VII: Sẵn sàng", text_color="#94a3b8"))

        threading.Thread(target=_fetch, daemon=True).start()
        self.after(3000, self._update_gpu_telemetry)

    def _run_diagnostic(self):
        self.txt_diag.delete("1.0", "end")
        self.txt_diag.insert("end", "=== BẮT ĐẦU CHẨN ĐOÁN MÔI TRƯỜNG ROCM ===\n\n")

        def _worker():
            cmd = [
                str(VENV_PYTHON), "-c",
                "import torch; print(f'PyTorch: {torch.__version__}'); "
                "print(f'ROCm/CUDA Available: {torch.cuda.is_available()}'); "
                "print(f'Device Name: {torch.cuda.get_device_name(0)}'); "
                "print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB'); "
                "from ultralytics import YOLO; print('Ultralytics YOLO: OK'); "
                "from lada.models.basicvsrpp.mmagic.basicvsr_plusplus_net import BasicVSRPlusPlusNet; print('BasicVSR++: OK'); "
            ]
            env = os.environ.copy()
            env["HSA_OVERRIDE_GFX_VERSION"] = "9.0.6"
            env["ROCM_PATH"] = "/opt/rocm"
            env["PATH"] = f"/opt/rocm/bin:{env.get('PATH', '')}"

            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
                for line in proc.stdout:
                    self.after(0, lambda l=line: self.txt_diag.insert("end", l))
                proc.wait()
                if proc.returncode == 0:
                    self.after(0, lambda: self.txt_diag.insert("end", "\n✔ TOÀN BỘ HỆ THỐNG ROCM GFX906 ĐẠT CHUẨN 100%!\n"))
                else:
                    self.after(0, lambda: self.txt_diag.insert("end", f"\n✖ Chẩn đoán có cảnh báo (Exit code: {proc.returncode})\n"))
            except Exception as e:
                self.after(0, lambda: self.txt_diag.insert("end", f"Lỗi: {e}\n"))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_start_click(self):
        inp = self.entry_input.get().strip()
        if not inp:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn tệp video hoặc thư mục đầu vào!")
            return
        if not os.path.exists(inp):
            messagebox.showerror("Lỗi", "Đường dẫn đầu vào không tồn tại!")
            return

        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.stop_requested = False
        self.lbl_status.configure(text="Đang xử lý...")
        self.prog_bar.set(0.0)
        self.lbl_speed.configure(text="⚡ Tốc độ: Đang tính...")
        self.lbl_eta.configure(text="⏱ Ước tính: Đang chờ...")

        self.current_worker = threading.Thread(target=self._process_worker, args=(inp,), daemon=True)
        self.current_worker.start()

    def _on_stop_click(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn dừng tiến trình phục hồi?"):
            self.stop_requested = True
            if self.active_proc:
                try:
                    self.active_proc.terminate()
                except Exception:
                    pass
            self.log("[HỆ THỐNG] Người dùng đã yêu cầu dừng tiến trình.")
            self._reset_ui_state()

    def _reset_ui_state(self):
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_status.configure(text="Sẵn sàng")
        if hasattr(self, 'lbl_stage'):
            self.lbl_stage.configure(text="📍 Công đoạn: Sẵn sàng", text_color="#34d399")

    def _detect_and_set_stage(self, line):
        if not hasattr(self, 'lbl_stage'):
            return
        if "[Khởi tạo]" in line:
            self.after(0, lambda: self.lbl_stage.configure(text="🎬 Công đoạn: Khởi tạo thông số video...", text_color="#60a5fa"))
        elif "[Cấu hình]" in line:
            self.after(0, lambda: self.lbl_stage.configure(text="⚙️ Công đoạn: Tải mô hình AI & Cấu hình thiết bị...", text_color="#818cf8"))
        elif "[YOLO Quét]" in line:
            self.after(0, lambda: self.lbl_stage.configure(text="🔍 Công đoạn: Đang quét phát hiện mosaic (YOLO)...", text_color="#f59e0b"))
        elif "[Gom cảnh" in line:
            self.after(0, lambda: self.lbl_stage.configure(text="📦 Công đoạn: Đã phát hiện mosaic - Đang gom clip cho AI GPU...", text_color="#fb923c"))
        elif "[AI Phục hồi GPU]" in line:
            if "Hoàn tất" in line:
                self.after(0, lambda: self.lbl_stage.configure(text="✔ Công đoạn: Đã hoàn tất AI clip trên GPU AMD", text_color="#10b981"))
            else:
                self.after(0, lambda: self.lbl_stage.configure(text="🚀 Công đoạn: GPU AMD Radeon Pro VII đang chạy AI BasicVSR++...", text_color="#38bdf8"))
        elif "[Ghép khung hình]" in line:
            self.after(0, lambda: self.lbl_stage.configure(text="🧩 Công đoạn: Đang hòa trộn khung hình phục hồi vào video...", text_color="#a78bfa"))
        elif "[Âm thanh]" in line:
            self.after(0, lambda: self.lbl_stage.configure(text="🎵 Công đoạn: Đang trích xuất và đồng bộ âm thanh gốc...", text_color="#e879f9"))
        elif "[Hoàn thành]" in line:
            self.after(0, lambda: self.lbl_stage.configure(text="🎉 Công đoạn: Hoàn tất xuất sắc video!", text_color="#22c55e"))

    def _update_stage(self, text, color):
        if hasattr(self, 'lbl_stage'):
            self.lbl_stage.configure(text=text, text_color=color)

    def _update_progress(self, pct, cur_f, tot_f, speed_val, rem_time, time_done=""):
        self.prog_bar.set(pct / 100.0)
        if tot_f > 0:
            self.lbl_frames.configure(text=f"Khung hình: {cur_f:,} / {tot_f:,} ({pct}%)")
        else:
            self.lbl_frames.configure(text=f"Khung hình: {cur_f:,} ({pct}%)")

        if speed_val and speed_val != "?":
            try:
                s_float = float(speed_val)
                self.lbl_speed.configure(text=f"⚡ Tốc độ: {s_float:.1f} fps")
            except Exception:
                self.lbl_speed.configure(text=f"⚡ Tốc độ: {speed_val} fps")

        if rem_time and rem_time != "?":
            self.lbl_eta.configure(text=f"⏱ Còn lại: ~{rem_time}")
        else:
            self.lbl_eta.configure(text="⏱ Còn lại: Đang tính...")

        if time_done and hasattr(self, 'lbl_elapsed'):
            self.lbl_elapsed.configure(text=f"Đã chạy: {time_done}")

    def _process_worker(self, input_path):
        out_dir = self.entry_output.get().strip()
        det_model = self.cmb_det.get().strip()
        rest_model = self.cmb_rest.get().strip()
        clip_len = self.cmb_clip_len.get().strip()
        encoder = self.cmb_encoder.get().split()[0].strip()
        fp16 = self.var_fp16.get()
        face_ignore = self.var_face_ignore.get()

        cmd = [
            *LADA_CLI_CMD,
            "--input", input_path,
            "--device", "cuda:0",
            "--mosaic-detection-model", det_model,
            "--mosaic-restoration-model", rest_model,
            "--max-clip-length", clip_len,
            "--encoding-preset", encoder,
        ]
        if out_dir:
            cmd.extend(["--output", out_dir])
        if fp16:
            cmd.append("--fp16")
        else:
            cmd.append("--no-fp16")
        if face_ignore:
            cmd.append("--detect-face-mosaics")

        env = os.environ.copy()
        env["HSA_OVERRIDE_GFX_VERSION"] = "9.0.6"
        env["ROCM_PATH"] = "/opt/rocm"
        env["HIP_VISIBLE_DEVICES"] = "0"
        env["ROCR_VISIBLE_DEVICES"] = "0"
        env["PATH"] = f"/opt/rocm/bin:/home/duy/.local/bin:{env.get('PATH', '')}"
        env["LD_LIBRARY_PATH"] = f"/opt/rocm/lib:{env.get('LD_LIBRARY_PATH', '')}"
        env["PYTORCH_CUDA_ALLOC_CONF"] = "garbage_collection_threshold:0.8,max_split_size_mb:512"
        env["LADA_MODEL_WEIGHTS_DIR"] = str(MODEL_WEIGHTS_DIR)
        env["OMP_NUM_THREADS"] = "4"
        env["OPENCV_FOR_THREADS_NUM"] = "4"
        env["OPENBLAS_NUM_THREADS"] = "4"
        env["MKL_NUM_THREADS"] = "4"
        env["OMP_WAIT_POLICY"] = "PASSIVE"
        env["PYTHONUNBUFFERED"] = "1"

        self.log(f"=== KHỞI CHẠY LADA ROCM STUDIO (AMD RADEON PRO VII) ===")
        self.log(f"Lệnh thực thi: {' '.join(cmd)}\n")

        t0 = time.time()
        total_frames = 0
        next_log_pct = 10
        last_log_time = t0

        prog_pattern = re.compile(
            r'(Processing video:\s*(\d+)%\|.*?\|Processed:\s*([^\s(]+)\s*\((\d+)f\)'
            r'(?:.*?Remaining:\s*([^\s(]+)(?:\s*\((?:(\d+)f|\?)\))?)?'
            r'(?:.*?Speed:\s*([\d.]+|\?)(?:fps)?)?)'
            r'(.*)$'
        )

        try:
            self.active_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
                cwd=str(SCRIPT_DIR),
                bufsize=1
            )

            buf = ""
            while True:
                if self.stop_requested:
                    break
                char = self.active_proc.stdout.read(1)
                if not char:
                    break
                if char in ("\r", "\n"):
                    if buf:
                        line = buf.strip()
                        buf = ""

                        # 1. Phát hiện tổng số frames từ thông báo Khởi tạo
                        if "frames (" in line and total_frames == 0:
                            m_tot = re.search(r"(\d+)\s*frames", line)
                            if m_tot:
                                total_frames = int(m_tot.group(1))

                        # 2. Xử lý dòng Tiến độ (tqdm)
                        m = prog_pattern.search(line)
                        if m:
                            pct = int(m.group(2))
                            time_done = m.group(3)
                            cur_f = int(m.group(4))
                            rem_time = m.group(5) or "?"
                            rem_f = m.group(6)
                            speed_str = m.group(7)
                            trailing = m.group(8).strip()

                            tot_f = total_frames if total_frames > 0 else (cur_f + int(rem_f) if rem_f else cur_f)

                            self.after(0, lambda p=pct, c=cur_f, t=tot_f, s=speed_str, e=rem_time, td=time_done:
                                       self._update_progress(p, c, t, s, e, td))

                            # Nếu có log kỹ thuật dính kèm sau thanh tiến độ -> ghi riêng vào log kỹ thuật
                            if trailing:
                                ts = time.strftime("[%H:%M:%S] ")
                                self.log(f"{ts}{trailing}")
                                self._detect_and_set_stage(trailing)

                            # Chỉ ghi nhận mốc tiến độ vào log kỹ thuật mỗi 10% hoặc 60s để tránh spam
                            now = time.time()
                            if pct >= next_log_pct or (now - last_log_time >= 60.0 and cur_f > 0):
                                ts = time.strftime("[%H:%M:%S] ")
                                spd_fmt = f"{float(speed_str):.1f} fps" if (speed_str and speed_str != "?") else "đang tính"
                                self.log(f"{ts}⚡ [Tiến độ] Đã xuất {cur_f:,}/{tot_f:,} frames ({pct}%) • Tốc độ: {spd_fmt} • Còn: ~{rem_time}")
                                next_log_pct = ((pct // 10) + 1) * 10
                                last_log_time = now
                        else:
                            # 3. Dòng này thuần túy là Nhật ký Kỹ thuật (Technical Log)!
                            ts = time.strftime("[%H:%M:%S] ")
                            self.log(f"{ts}{line}")
                            self._detect_and_set_stage(line)
                else:
                    buf += char

            self.active_proc.wait()
            ret = self.active_proc.returncode
            elapsed = time.time() - t0

            if ret == 0 and not self.stop_requested:
                self.log(f"\n✔ HOÀN TẤT PHỤC HỒI XUẤT SẮC! (Tổng thời gian: {elapsed:.1f} giây)")
                self.after(0, lambda: self.lbl_status.configure(text="Hoàn tất thành công!"))
                self.after(0, lambda: self._update_stage("🎉 Công đoạn: Hoàn tất xuất sắc video!", "#22c55e"))
                self.after(0, lambda: messagebox.showinfo("Thành công", f"Đã phục hồi video thành công trong {elapsed:.1f}s!"))
            elif self.stop_requested:
                self.log("\n⏹ Tiến trình đã bị hủy bởi người dùng.")
            else:
                self.log(f"\n✖ Xử lý kết thúc với mã lỗi: {ret}")
                self.after(0, lambda: self.lbl_status.configure(text="Lỗi xử lý"))
                self.after(0, lambda: self._update_stage("✖ Đã xảy ra lỗi khi xử lý", "#ef4444"))

        except Exception as ex:
            self.log(f"\n✖ Lỗi ngoại lệ: {ex}")
        finally:
            self.active_proc = None
            self.after(0, self._reset_ui_state)


if __name__ == "__main__":
    app = LadaRocmApp()
    app.mainloop()
