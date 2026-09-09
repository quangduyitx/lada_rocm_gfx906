# Hướng dẫn Cài đặt ROCm 7.14 & PyTorch 2.13 cho AMD GFX906

Tài liệu này hướng dẫn chi tiết quy trình thiết lập toàn diện từ hệ điều hành, driver ROCm 7.14 (TheRock build từ [mixa3607/ML-gfx906](https://github.com/mixa3607/ML-gfx906)), PyTorch 2.13 cho kiến trúc **AMD GFX906** (Radeon Instinct MI50 / MI60, Radeon Pro VII, Radeon VII, Vega 20) đến việc chạy hoàn chỉnh ứng dụng **Lada - ROCm GFX906 Edition** trên **Ubuntu 24.04 LTS (noble)** và **Linux Mint 22.x**.

---

## 1. Yêu cầu Hệ thống & Phần cứng
* **GPU hỗ trợ:** AMD kiến trúc GFX906:
  * AMD Radeon Instinct MI50 (16GB / 32GB HBM2)
  * AMD Radeon Instinct MI60 (32GB HBM2)
  * AMD Radeon Pro VII (32GB HBM2)
  * AMD Radeon VII (16GB HBM2)
* **Hệ điều hành:**
  * Ubuntu 24.04 LTS (`noble`)
  * Linux Mint 22.x (dựa trên `noble`)
* **Python:** Python 3.12 (khuyên dùng `python3.12-venv`)

---

## 2. Bước 1: Cài đặt ROCm 7.14 (TheRock Build)

> [!WARNING]
> **Tuyệt đối không dùng chung với repo chính thức của AMD (`repo.radeon.com`)!** Việc này sẽ gây xung đột gói APT nghiêm trọng (`amdgpu-dkms`, `hip-runtime-amd`, v.v.).

### 2.1 Cài đặt dependencies hệ thống & APT Key
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ffmpeg python3.12 python3.12-venv python3-pip

# Thêm GPG Key của kho GFX906
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://s3.arkprojects.space/apt-gfx906/ubuntu/gpg -o /etc/apt/keyrings/apt-gfx906.asc
sudo chmod a+r /etc/apt/keyrings/apt-gfx906.asc
```

### 2.2 Thêm nguồn APT
> [!NOTE]
> Luôn đặt `Suites: noble` (kể cả khi chạy trên Linux Mint 22.x có codename là `zena`, do kho lưu trữ chỉ hỗ trợ nhánh `noble`).

```bash
sudo tee /etc/apt/sources.list.d/gfx906.sources <<EOF
Types: deb
URIs: https://s3.arkprojects.space/apt-gfx906/ubuntu
Suites: noble
Components: main
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/apt-gfx906.asc
EOF

sudo apt-get update
```

### 2.3 Cài đặt gói ROCm GFX906
```bash
sudo apt-get install -y amdrocm7.14-gfx906
```

### 2.4 Cấp quyền truy cập GPU cho tài khoản
```bash
sudo usermod -a -G render,video $USER
# Áp dụng quyền ngay trong phiên làm việc hiện tại mà không cần khởi động lại:
newgrp render
```

### 2.5 Cấu hình biến môi trường ROCm toàn hệ thống
Tạo file cấu hình `/etc/profile.d/rocm.sh`:
```bash
sudo tee /etc/profile.d/rocm.sh <<'EOF'
export ROCM_PATH=/opt/rocm
export PATH=$ROCM_PATH/bin:$PATH
export LD_LIBRARY_PATH=$ROCM_PATH/lib:$LD_LIBRARY_PATH
export HSA_OVERRIDE_GFX_VERSION=9.0.6
EOF

# Nạp biến môi trường cho shell hiện tại
source /etc/profile.d/rocm.sh
```

---

## 3. Bước 2: Tinh chỉnh Kernel & Tối ưu Hiệu năng GPU (Khuyên dùng)

### 3.1 Mở khóa PowerPlay & Cơ chế Tự phục hồi GPU
Để tránh tình trạng tràn timeout TDR làm crash desktop khi GPU vừa xuất hình vừa xử lý AI:
```bash
echo "options amdgpu lockup_timeout=60000 gpu_recovery=1 ppfeaturemask=0xffffffff" | sudo tee /etc/modprobe.d/amdgpu.conf
```

Nếu muốn nạp vĩnh viễn vào bootloader GRUB:
1. Mở `/etc/default/grub` và thêm vào `GRUB_CMDLINE_LINUX_DEFAULT`:
   ```text
   amdgpu.ppfeaturemask=0xffffffff amdgpu.gpu_recovery=1
   ```
2. Chạy: `sudo update-grub && sudo update-initramfs -u -k all`

### 3.2 Chuyển Power Profile sang chế độ Compute
Khóa profile tính toán tải nặng (giữ xung HBM2 1000MHz liên tục, giảm latency):
```bash
# Thay cardX bằng card của bạn (ví dụ card0 hoặc card1)
echo 5 | sudo tee /sys/class/drm/card0/device/pp_power_profile_mode
```

---

## 4. Bước 3: Cài đặt Môi trường Ảo & PyTorch 2.13.0 GFX906

Bản build PyTorch 2.13.0 cho GFX906 được biên dịch sẵn cho Python 3.12 (`cp312`) trên nền tảng ROCm 7.14.

### 4.1 Khởi tạo môi trường ảo Python 3.12
```bash
cd lada_rocm
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
```

### 4.2 Tải và Cài đặt PyTorch Wheels
```bash
mkdir -p /tmp/torch-gfx906 && cd /tmp/torch-gfx906
curl -O https://s3.arkprojects.space/py-gfx906/rocm7.14/torch-v2.13.0+gfx906.20260802001858/index.txt

# Tải tất cả file wheel (.whl) được liệt kê trong index.txt
while read -r f; do
  curl -O "https://s3.arkprojects.space/py-gfx906/rocm7.14/torch-v2.13.0+gfx906.20260802001858/$f"
done < index.txt

# Cài đặt vào môi trường ảo
pip install *.whl
cd - && rm -rf /tmp/torch-gfx906
```

### 4.3 Kiểm tra xác thực nhận diện GPU
```bash
python3 -c "import torch; print('PyTorch Version:', torch.__version__); print('ROCm CUDA Available:', torch.cuda.is_available()); print('Device Name:', torch.cuda.get_device_name(0))"
```
*Kết quả mẫu:*
```text
PyTorch Version: 2.13.0+gfx906.20260802001858
ROCm CUDA Available: True
Device Name: AMD Radeon Pro VII
```

---

## 5. Bước 4: Cài đặt Dependencies của LADA & Áp dụng Bản vá

### 5.1 Cài đặt các thư viện bổ trợ
```bash
pip install "ultralytics==8.4.4" \
            "opencv-python==4.12.0.88" \
            "mmengine==0.10.7" \
            "av>=16.1.0" \
            customtkinter packaging requests tqdm wcwidth

# Cài đặt gói lada ở chế độ editable
pip install -e . --no-deps
```

### 5.2 Áp dụng các bản vá hệ thống
```bash
patch -u -p1 -d .venv/lib/python3.12/site-packages < patches/increase_mms_time_limit.patch
patch -u -p1 -d .venv/lib/python3.12/site-packages < patches/remove_ultralytics_telemetry.patch
patch -u -p1 -d .venv/lib/python3.12/site-packages < patches/fix_loading_mmengine_weights_on_torch26_and_higher.diff
```

### 5.3 Biên dịch ngôn ngữ (Tùy chọn)
```bash
bash translations/compile_po.sh
```

---

## 6. Bước 5: Tải AI Model Weights

Tạo thư mục và tải các trọng số mô hình:
```bash
mkdir -p model_weights

# Mô hình nhận diện Mosaic (YOLO v4 Fast - Khuyên dùng)
wget 'https://huggingface.co/ladaapp/lada/resolve/main/lada_mosaic_detection_model_v4_fast.pt?download=true' -O model_weights/lada_mosaic_detection_model_v4_fast.pt

# Mô hình nhận diện Mosaic (YOLO v4 Accurate)
wget 'https://huggingface.co/ladaapp/lada/resolve/main/lada_mosaic_detection_model_v4_accurate.pt?download=true' -O model_weights/lada_mosaic_detection_model_v4_accurate.pt

# Mô hình phục hồi BasicVSR++ v1.2
wget 'https://huggingface.co/ladaapp/lada/resolve/main/lada_mosaic_restoration_model_generic_v1.2.pth?download=true' -O model_weights/lada_mosaic_restoration_model_generic_v1.2.pth
```

*(Nếu đã có sẵn từ thư mục lada khác, bạn có thể tạo symlink sang thư mục đó để tiết kiệm dung lượng ổ cứng).*

---

## 7. Bước 6: Khởi chạy LADA ROCm

### 7.1 Chạy Giao diện Đồ họa (ROCm Studio GUI)
```bash
./lada_rocm.sh
# Hoặc khởi chạy trực tiếp qua python:
python3 lada_rocm_gui.py
```
Giao diện hiển thị thời gian thực Telemetry của GPU AMD (Nhiệt độ, Công suất W, Mức dùng VRAM và GPU), đồng thời bóc tách tiến độ % và tốc độ it/s sang bảng đo lường riêng biệt.

### 7.2 Chạy Dòng lệnh (CLI)
```bash
./lada_rocm_cli.sh --input "/duong_dan/video.mp4" --device cuda:0
```

### 7.3 Tối ưu CPU Threading & Hybrid Video Encoding
1. **Kiểm soát luồng CPU:** Khi chạy Lada, launcher script đã cấu hình sẵn:
   ```bash
   export OMP_WAIT_POLICY=PASSIVE
   export OMP_NUM_THREADS=4
   export OPENCV_FOR_THREADS_NUM=4
   ```
   giúp ngăn chặn hiện tượng busy-wait làm CPU bị nghẽn 100%.
2. **Chế độ Hybrid GPU Encoding (AMD AI + NVIDIA NVENC):**
   Nếu máy tính trang bị song song card NVIDIA (ví dụ NVIDIA CMP 40HX hoặc RTX series):
   - AMD GFX906 xử lý toàn bộ AI Forward Pass.
   - Chọn preset mã hóa `--encoder-preset hevc-nvidia-gpu-hq` để card NVIDIA xuất video bằng NVENC với tốc độ 300 - 600 FPS mà không tiêu tốn CPU.

---

## 8. Lời cảm ơn (Acknowledgements)
* Dự án chân thành cảm ơn **[mixa3607](https://github.com/mixa3607)** và kho lưu trữ **[mixa3607/ML-gfx906](https://github.com/mixa3607/ML-gfx906)** cùng cộng đồng **[Ark Projects GFX906 Wiki](https://arkprojects.space/wiki/AMD_GFX906)** đã bảo trì các bản build ROCm 7.14 TheRock và PyTorch wheels xuất sắc dành riêng cho kiến trúc AMD GFX906.
