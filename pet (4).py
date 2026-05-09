import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk, ImageDraw
import random
import math
import os
from collections import deque
import cv2
import numpy as np

class DesktopPet:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("桌面宠物")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', '#010101')
        self.root.config(bg='#010101')
        
        self.canvas = tk.Canvas(self.root, width=110, height=180, 
                                bg='#010101', highlightthickness=0)
        self.canvas.pack()
        
        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        self.x = random.randint(100, self.screen_w - 200)
        self.y = random.randint(100, self.screen_h - 250)
        self.root.geometry(f'110x180+{self.x}+{self.y}')
        
        self.direction = 1
        self.speed = 1.5
        self.state = 'idle'
        self.state_timer = 0
        self.frame = 0
        
        self.drag_x = 0
        self.drag_y = 0
        self.dragging = False
        
        self.avatar_original = None
        self.avatar_img = None
        self.body_img = None
        self.current_body = None
        
        self.bubble_text = ''
        self.bubble_timer = 0
        self.phrases = ['你好呀~', '摸摸我！', '今天也要加油！', '工作辛苦了~', '陪我玩~']
        
        self.bodies = {
            'Q版西装': (r'C:\Users\yyzb\Desktop\Qsuit.png', 0.5, 0.22, 40, True),
            '西装':    (r'C:\Users\yyzb\Desktop\suit.png',  0.5, 0.22, 40, True),
            'Q版裙子': (r'C:\Users\yyzb\Desktop\Qdress.png',0.5, 0.22, 40, True),
            '裙子':    (r'C:\Users\yyzb\Desktop\dress.png', 0.5, 0.22, 40, True),
            '奶牛':    (r'C:\Users\yyzb\Desktop\cow.png',   0.20, 0.32, 35, False),
            '马':      (r'C:\Users\yyzb\Desktop\horse.png', 0.30, 0.28, 35, False),
        }
        
        self.avatar_x_ratio = 0.5
        self.avatar_y_ratio = 0.22
        self.avatar_size = 40
        self.is_upright = True
        
        # 加载人脸检测器
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        
        self.canvas.bind('<Button-1>', self.on_click)
        self.canvas.bind('<B1-Motion>', self.on_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_release)
        self.canvas.bind('<Button-3>', self.show_menu)
        
        self.animate()
        self.root.mainloop()

    # ── 图片工具 ──────────────────────────────────────────

    def try_load_image(self, path):
        candidates = [path, path+'.jpg', path+'.png',
                      path.replace('.png','.png.jpg'), path.replace('.png','.jpg')]
        for p in candidates:
            if os.path.exists(p):
                print(f'找到: {p}')
                return Image.open(p).convert('RGBA')
        folder = os.path.dirname(path)
        base = os.path.splitext(os.path.basename(path))[0]
        if os.path.exists(folder):
            for f in os.listdir(folder):
                if f.startswith(base):
                    full = os.path.join(folder, f)
                    print(f'模糊匹配: {full}')
                    return Image.open(full).convert('RGBA')
        print(f'找不到: {path}')
        return None

    def binarize_alpha(self, img):
        """把 alpha 通道二值化（<128→0，>=128→255），消除半透明边缘噪点"""
        r, g, b, a = img.split()
        a = a.point(lambda x: 0 if x < 128 else 255)
        return Image.merge('RGBA', (r, g, b, a))

    def remove_bg_flood(self, img):
        """从四角泛洪去除白色背景"""
        w, h = img.size
        data = list(img.getdata())
        visited = set()
        queue = deque()
        for corner in [(0,0),(w-1,0),(0,h-1),(w-1,h-1)]:
            queue.append(corner)
            visited.add(corner)
        def is_bg(p):
            return p[3] < 30 or (p[0]>210 and p[1]>210 and p[2]>210)
        while queue:
            x, y = queue.popleft()
            idx = y*w+x
            if is_bg(data[idx]):
                data[idx] = (1,1,1,0)
                for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nx,ny = x+dx, y+dy
                    if 0<=nx<w and 0<=ny<h and (nx,ny) not in visited:
                        visited.add((nx,ny))
                        queue.append((nx,ny))
        img.putdata(data)
        return img

    def to_tk_image(self, img):
        """RGBA → RGB，透明区域填 #010101，tkinter 识别为透明色"""
        img = img.convert('RGBA')
        r, g, b, a = img.split()
        # 二值化 alpha，彻底消除半透明边缘
        a = a.point(lambda x: 0 if x < 128 else 255)
        bg = Image.new('RGB', img.size, (1, 1, 1))
        bg.paste(Image.merge('RGBA',(r,g,b,a)), mask=a)
        return ImageTk.PhotoImage(bg)

    def load_body(self, path):
        try:
            img = self.try_load_image(path)
            if img is None:
                return None
            # 判断图片是否已有透明通道
            alpha_data = list(img.split()[3].getdata())
            has_transparency = min(alpha_data) < 50
            if not has_transparency:
                # 白底图片 → 泛洪去背景
                img = self.remove_bg_flood(img)
            # 统一二值化 alpha
            img = self.binarize_alpha(img)
            w, h = img.size
            ratio = min(100/w, 110/h)
            img = img.resize((int(w*ratio), int(h*ratio)), Image.LANCZOS)
            return img
        except Exception as e:
            print(f'加载失败: {e}')
            return None

    # ── 人脸检测抠头 ──────────────────────────────────────

    def detect_and_crop_face(self, pil_img):
        """用 OpenCV 检测人脸，裁出头部区域（含少量留白）"""
        # PIL → OpenCV
        img_cv = cv2.cvtColor(np.array(pil_img.convert('RGB')), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=4, minSize=(30,30)
        )
        
        if len(faces) > 0:
            # 取面积最大的脸
            x, y, w, h = max(faces, key=lambda f: f[2]*f[3])
            # 上方多留一点空间（发顶），下方少留（不要脖子）
            pad_top    = int(h * 0.45)
            pad_side   = int(w * 0.25)
            pad_bottom = int(h * 0.10)
            x1 = max(0, x - pad_side)
            y1 = max(0, y - pad_top)
            x2 = min(pil_img.width,  x + w + pad_side)
            y2 = min(pil_img.height, y + h + pad_bottom)
            cropped = pil_img.crop((x1, y1, x2, y2))
            print(f'检测到人脸，裁剪区域: ({x1},{y1})-({x2},{y2})')
            return cropped
        else:
            # 没检测到脸 → fallback：取图片上半部分中心正方形
            print('未检测到人脸，使用中心上部裁剪')
            w, h = pil_img.size
            side = min(w, h//2)
            left = (w - side) // 2
            top  = 0
            return pil_img.crop((left, top, left+side, top+side))

    def make_circle_avatar(self, img, size=40):
        """裁出圆形头像（先抠脸再做圆形）"""
        face = self.detect_and_crop_face(img)
        face = face.resize((size, size), Image.LANCZOS).convert('RGBA')
        
        mask = Image.new('L', (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        
        result = Image.new('RGBA', (size, size), (0,0,0,0))
        result.paste(face, mask=mask)
        
        bordered = Image.new('RGBA', (size+4, size+4), (0,0,0,0))
        draw2 = ImageDraw.Draw(bordered)
        draw2.ellipse((0, 0, size+3, size+3), outline='white', width=2)
        bordered.paste(result, (2,2), result)
        return bordered

    # ── 绘制四肢 ─────────────────────────────────────────

    def draw_limbs(self, body_y_offset):
        if not self.is_upright:
            return
        t = self.frame * 0.18
        walk_amp = 12 if self.state == 'walk' else 2
        cx = 55
        body_top    = 50  + int(body_y_offset)
        body_bottom = 155 + int(body_y_offset)
        shoulder_y  = body_top + (body_bottom-body_top)*0.28
        hip_y       = body_top + (body_bottom-body_top)*0.58
        leg_len, arm_len = 19, 14
        shoulder_offset, hip_offset = 9, 6
        color = '#888888'

        for side, leg_a, arm_a in [
            (-1, math.sin(t)*walk_amp,           math.sin(t+math.pi)*(walk_amp*0.7)),
            ( 1, math.sin(t+math.pi)*walk_amp,   math.sin(t)*(walk_amp*0.7)),
        ]:
            # 腿
            hx, hy = cx+side*hip_offset, hip_y
            self.canvas.create_line(hx, hy,
                hx+math.sin(math.radians(leg_a))*leg_len,
                hy+math.cos(math.radians(leg_a))*leg_len,
                fill=color, width=4, capstyle='round')
            # 臂
            sx, sy = cx+side*shoulder_offset, shoulder_y
            self.canvas.create_line(sx, sy,
                sx+math.sin(math.radians(arm_a))*arm_len,
                sy+math.cos(math.radians(arm_a))*arm_len,
                fill=color, width=3, capstyle='round')

    # ── 主绘制循环 ────────────────────────────────────────

    def draw_pet(self):
        self.canvas.delete('all')
        body_y_offset = math.sin(self.frame*0.1)*2
        tilt = math.sin(self.frame*0.18)*3 if self.state=='walk' else 0

        if self.body_img:
            bd = self.body_img.copy()
            if self.direction == -1 and self.is_upright:
                bd = bd.transpose(Image.FLIP_LEFT_RIGHT)
            if tilt:
                bd = bd.rotate(-tilt, expand=False, resample=Image.BICUBIC)
            body_tk = self.to_tk_image(bd)
            self.canvas.body_tk = body_tk
            bh = self.body_img.size[1]
            body_cy = 150 - bh//2 + body_y_offset
            self.draw_limbs(body_y_offset)
            self.canvas.create_image(55, body_cy, image=body_tk, anchor='center')
        else:
            self.canvas.create_rectangle(5,40,105,155, fill='#dddddd', outline='')
            self.canvas.create_text(55,97, text='右键选择身体',
                                    fill='#666666', font=('Arial',7))
            self.draw_limbs(body_y_offset)

        av_x = int(110*self.avatar_x_ratio)
        av_y = int(180*self.avatar_y_ratio)+int(body_y_offset)
        if self.avatar_img:
            av_tk = self.to_tk_image(self.avatar_img)
            self.canvas.avatar_tk = av_tk
            self.canvas.create_image(av_x, av_y, image=av_tk, anchor='center')
        else:
            r = self.avatar_size//2
            self.canvas.create_oval(av_x-r,av_y-r,av_x+r,av_y+r,
                                    fill='#eeeeee', outline='white', width=2)
            self.canvas.create_text(av_x, av_y, text='上传头像',
                                    fill='#999999', font=('Arial',6))

        if self.bubble_text and self.bubble_timer > 0:
            self.canvas.create_rectangle(5,1,105,16, fill='white', outline='#dddddd')
            self.canvas.create_text(55,8, text=self.bubble_text,
                                    font=('Arial',6), fill='#333333')

    def animate(self):
        self.frame += 1
        self.state_timer -= 1
        if self.bubble_timer > 0:
            self.bubble_timer -= 1
        if self.state_timer <= 0:
            self.change_state()
        if self.state=='walk' and not self.dragging:
            self.x += self.speed*self.direction
            if self.x > self.screen_w-110: self.direction = -1
            if self.x < 0:                 self.direction =  1
            self.root.geometry(f'110x180+{int(self.x)}+{int(self.y)}')
        self.draw_pet()
        self.root.after(50, self.animate)

    def change_state(self):
        self.state = random.choice(['idle','idle','walk','walk'])
        self.state_timer = random.randint(80, 200)
        self.speed = random.uniform(1, 2.5)
        if random.random() < 0.25:
            self.bubble_text = random.choice(self.phrases)
            self.bubble_timer = 50

    def on_click(self, e):
        self.drag_x = e.x_root-self.x
        self.drag_y = e.y_root-self.y
        self.dragging = True
        self.bubble_text = random.choice(['抓到我了！','放我下来~','嘿！'])
        self.bubble_timer = 40

    def on_drag(self, e):
        if self.dragging:
            self.x = e.x_root-self.drag_x
            self.y = e.y_root-self.drag_y
            self.root.geometry(f'110x180+{int(self.x)}+{int(self.y)}')

    def on_release(self, e):
        self.dragging = False

    def upload_avatar(self):
        path = filedialog.askopenfilename(
            title='选择头像图片',
            filetypes=[('图片文件','*.png *.jpg *.jpeg')]
        )
        if path:
            self.avatar_original = Image.open(path).convert('RGBA')
            self.avatar_img = self.make_circle_avatar(self.avatar_original, self.avatar_size)
            self.bubble_text = '头像换好啦！'
            self.bubble_timer = 50

    def select_body(self, name):
        config = self.bodies.get(name)
        if not config: return
        path, ax, ay, asize, upright = config
        result = self.load_body(path)
        if result:
            self.body_img = result
            self.current_body = name
            self.avatar_x_ratio = ax
            self.avatar_y_ratio = ay
            self.avatar_size = asize
            self.is_upright = upright
            if self.avatar_original:
                self.avatar_img = self.make_circle_avatar(self.avatar_original, asize)
            self.bubble_text = f'换上{name}啦！'
            self.bubble_timer = 50
        else:
            self.bubble_text = '加载失败！'
            self.bubble_timer = 50

    def show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='📷 上传头像', command=self.upload_avatar)
        menu.add_separator()
        body_menu = tk.Menu(menu, tearoff=0)
        for name in self.bodies:
            body_menu.add_command(label=name, command=lambda n=name: self.select_body(n))
        menu.add_cascade(label='👗 选择身体', menu=body_menu)
        menu.add_separator()
        menu.add_command(label='❌ 退出', command=self.root.destroy)
        menu.post(e.x_root, e.y_root)

DesktopPet()
