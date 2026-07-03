import os
import glob
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk, ImageFont, ImageDraw
import pygame

# --- 설정 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  
FONT_PATH = os.path.join(BASE_DIR, "font.ttf") 
IMAGE_DELAY = 5000  

# 역 목록 (진접 -> 사당 방향)
BASE_STATIONS = ["진접", "총신대입구", "사당"] 

# 초기 해상도 설정
CONTROL_SIZE = "800x480"
DISPLAY_SIZE = (1920, 1080) 

class SubwaySystem:
    def __init__(self, root):
        self.root = root
        self.root.title("안내방송 제어 화면")
        self.root.geometry(f"{CONTROL_SIZE}+0+0")
        
        # 오디오 초기화 (리눅스 오디오 에러 방지를 위해 예외 처리 추가)
        try:
            pygame.mixer.init()
        except Exception as e:
            print(f"[경고] 오디오 시스템 초기화 실패 (리눅스 오디오 드라이버 문제일 수 있음): {e}")

        # 상태 변수
        self.direction = "진접행" 
        if self.direction == "진접행":
            self.active_stations = list(reversed(BASE_STATIONS))
        else:
            self.active_stations = list(BASE_STATIONS)
            
        self.station_idx = 0 
        self.is_standby = False
        self.departure_state = 0 
        self.image_loop_idx = 0
        self.is_playing_announce = False 
        
        # 전체화면 상태 변수
        self.control_fs = False
        self.display_fs = False
        self.text_offset_x = 0
        self.text_offset_y = 0
        
        # 디스플레이 창 설정
        self.display_window = tk.Toplevel(self.root)
        self.display_window.title("안내 화면")
        self.display_window.geometry(f"{DISPLAY_SIZE[0]}x{DISPLAY_SIZE[1]}+50+50")
        self.display_label = tk.Label(self.display_window, bg="black")
        self.display_label.pack(fill="both", expand=True)

        self.create_control_ui()
        self.setup_key_bindings() 
        self.update_display_loop()
        
        # (요청에 따라 강제 끌어올리기 기능 삭제됨)

    def create_control_ui(self):
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(expand=True)

        self.lbl_dest = tk.Label(self.main_frame, text=self.direction, font=("Helvetica", 16, "bold"), fg="blue")
        self.lbl_dest.grid(row=0, column=2, pady=10, sticky="e")
        
        tk.Button(self.main_frame, text="행선지변경", bg="#4169E1", fg="white", font=("Helvetica", 12), command=self.toggle_direction).grid(row=0, column=3, padx=10, pady=10)

        self.lbl_current = tk.Label(self.main_frame, text=f"이번 방송역: {self.active_stations[self.station_idx]}", font=("Helvetica", 14))
        self.lbl_current.grid(row=1, column=0, columnspan=2, pady=10, sticky="w")
        
        tk.Button(self.main_frame, text="출입문", bg="#1E90FF", fg="white", font=("Helvetica", 12), command=self.play_door).grid(row=1, column=2, padx=5)
        tk.Button(self.main_frame, text="대기", bg="#1E90FF", fg="white", font=("Helvetica", 12), command=self.toggle_standby).grid(row=1, column=3, padx=5)

        tk.Button(self.main_frame, text="출발화면/방송", bg="#4169E1", fg="white", font=("Helvetica", 12, "bold"), command=self.handle_departure).grid(row=2, column=2, columnspan=2, sticky="we", pady=10, padx=5)

        tk.Button(self.main_frame, text="◀ 이전역", bg="#FF6A6A", fg="white", font=("Helvetica", 14), command=lambda: self.change_station(-1)).grid(row=3, column=0, pady=20)
        
        self.btn_announce = tk.Button(self.main_frame, text="시 작", bg="#1E90FF", fg="white", font=("Helvetica", 16, "bold"), command=self.toggle_announce)
        self.btn_announce.grid(row=3, column=1, columnspan=2, sticky="we", padx=10)
        
        tk.Button(self.main_frame, text="다음역 ▶", bg="#FF6A6A", fg="white", font=("Helvetica", 14), command=lambda: self.change_station(1)).grid(row=3, column=3, pady=20)

    def setup_key_bindings(self):
        self.root.bind("<f>", self.toggle_control_fs)
        self.root.bind("<F>", self.toggle_control_fs)
        self.display_window.bind("<f>", self.toggle_display_fs)
        self.display_window.bind("<F>", self.toggle_display_fs)
        
        for win in (self.root, self.display_window):
            win.bind("<Up>", self.move_text_up)
            win.bind("<Down>", self.move_text_down)
            win.bind("<Left>", self.move_text_left)
            win.bind("<Right>", self.move_text_right)

    def toggle_control_fs(self, event=None):
        self.control_fs = not self.control_fs
        self.root.attributes("-fullscreen", self.control_fs)

    def toggle_display_fs(self, event=None):
        self.display_fs = not self.display_fs
        self.display_window.attributes("-fullscreen", self.display_fs)

    def move_text_up(self, event=None): self.text_offset_y -= 10
    def move_text_down(self, event=None): self.text_offset_y += 10
    def move_text_left(self, event=None): self.text_offset_x -= 10
    def move_text_right(self, event=None): self.text_offset_x += 10

    def check_lockout(self):
        return self.departure_state > 0

    def toggle_direction(self):
        if self.check_lockout(): return
        self.direction = "진접행" if self.direction == "사당행" else "사당행"
        if self.direction == "진접행":
            self.active_stations = list(reversed(BASE_STATIONS))
        else:
            self.active_stations = list(BASE_STATIONS)
            
        self.station_idx = 0 
        self.lbl_dest.config(text=self.direction)
        self.update_ui_labels()
        self.image_loop_idx = 0

    def find_audio_file(self, folder_path, base_name):
        for ext in [".wav", ".mp3", ".WAV", ".MP3"]:
            full_path = os.path.join(folder_path, base_name + ext)
            if os.path.exists(full_path): return full_path
        return None 

    def find_image_file(self, folder_path, base_name):
        for ext in [".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"]:
            full_path = os.path.join(folder_path, base_name + ext)
            if os.path.exists(full_path): return full_path
        return None

    def play_door(self):
        if self.check_lockout(): return
        audio_path = self.find_audio_file(BASE_DIR, "door")
        self.play_audio(audio_path)

    def toggle_standby(self):
        if self.check_lockout(): return
        self.is_standby = not self.is_standby

    def handle_departure(self):
        self.departure_state = (self.departure_state + 1) % 3
        if self.departure_state == 2:
            base_name = f"departure_{self.direction}"
            audio_path = self.find_audio_file(BASE_DIR, base_name)
            self.play_audio(audio_path)

    def change_station(self, delta):
        if self.check_lockout(): return
        new_idx = self.station_idx + delta
        if 0 <= new_idx < len(self.active_stations):
            self.station_idx = new_idx
            self.update_ui_labels()
            self.image_loop_idx = 0

    def toggle_announce(self):
        if self.check_lockout(): return
        if self.is_playing_announce:
            pygame.mixer.music.stop()
            self.is_playing_announce = False
            self.btn_announce.config(text="시 작", bg="#1E90FF")
        else:
            station_dir = os.path.join(BASE_DIR, self.active_stations[self.station_idx])
            audio_path = self.find_audio_file(station_dir, "announce")
            self.play_audio(audio_path, is_announce=True)

    def play_audio(self, path, is_announce=False):
        if path and os.path.exists(path):
            try:
                audio_file = open(path, "rb")
                pygame.mixer.music.load(audio_file)
                pygame.mixer.music.play()
                print(f"[오디오 재생] {path}")
                
                if is_announce:
                    self.is_playing_announce = True
                    self.btn_announce.config(text="중 지", bg="#FF4500") 
                    self.check_audio_end() 
                else:
                    if self.is_playing_announce:
                        self.is_playing_announce = False
                        self.btn_announce.config(text="시 작", bg="#1E90FF")
            except Exception as e:
                print(f"[오디오 에러] {path} 재생 실패: {e}")
        else:
            print(f"[오디오 없음] 경로를 확인하세요: {path}")

    def check_audio_end(self):
        if self.is_playing_announce:
            if not pygame.mixer.music.get_busy():
                self.is_playing_announce = False
                self.btn_announce.config(text="시 작", bg="#1E90FF")
            else:
                self.root.after(200, self.check_audio_end)

    def update_ui_labels(self):
        self.lbl_current.config(text=f"이번 방송역: {self.active_stations[self.station_idx]}")

    # --- 디스플레이 로직 ---
    def update_display_loop(self):
        current_station = self.active_stations[self.station_idx]
        station_dir = os.path.join(BASE_DIR, current_station)
        
        img_path = None
        
        # 1. 출발 상태 체크
        if self.departure_state in (1, 2):
            img_path = self.find_image_file(BASE_DIR, f"departure_{self.direction}")
            if not img_path: img_path = self.find_image_file(BASE_DIR, "departure")
            if not img_path: img_path = self.find_image_file(station_dir, "standby")
                
        # 2. 대기 상태 체크
        elif self.is_standby:
            img_path = self.find_image_file(station_dir, "standby")
            
        # 3. 반복 화면 상태
        else:
            loop_dir = os.path.join(station_dir, self.direction)
            if os.path.exists(loop_dir):
                images = []
                for f in os.listdir(loop_dir):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                        images.append(os.path.join(loop_dir, f))
                
                images = sorted(images)
                
                if images:
                    img_path = images[self.image_loop_idx % len(images)]
                    self.image_loop_idx += 1

        # 터미널에 현재 어떤 이미지를 로드하려고 하는지 로그 출력
        if img_path:
            print(f"[디스플레이] 이미지 렌더링 중: {img_path}")
        else:
            print(f"[디스플레이] 해당 상태의 이미지를 찾을 수 없어 검은 화면 표시됨. (역: {current_station}, 상태: {self.direction})")

        # 창 해상도 자동 감지
        win_w = self.display_label.winfo_width()
        win_h = self.display_label.winfo_height()
        if win_w < 10 or win_h < 10:  
            win_w, win_h = DISPLAY_SIZE

        # 폰트 로드
        try:
            font = ImageFont.truetype(FONT_PATH, 60)
        except IOError:
            try:
                font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 50)
            except IOError:
                font = ImageFont.load_default()

        # 이미지를 성공적으로 찾았을 때
        if img_path and os.path.exists(img_path):
            try:
                img = Image.open(img_path).convert("RGBA")
                
                try: resample_filter = Image.Resampling.LANCZOS
                except AttributeError: resample_filter = Image.ANTIALIAS
                
                img = img.resize((win_w, win_h), resample_filter)
                draw = ImageDraw.Draw(img)
                
                text_x = img.width - 250 + self.text_offset_x
                text_y = 30 + self.text_offset_y
                draw.text((text_x, text_y), self.direction, font=font, fill=(255, 255, 255, 255))
                
                self.tk_img = ImageTk.PhotoImage(img)
                self.display_label.config(image=self.tk_img)
            except Exception as e:
                print(f"[이미지 에러] {img_path} 렌더링 실패: {e}")
                
        # 이미지를 못 찾았을 때 (순수한 검은 화면)
        else:
            img = Image.new("RGBA", (win_w, win_h), "black")
            self.tk_img = ImageTk.PhotoImage(img)
            self.display_label.config(image=self.tk_img)

        self.root.after(IMAGE_DELAY, self.update_display_loop)

if __name__ == "__main__":
    root = tk.Tk()
    app = SubwaySystem(root)
    root.mainloop()