import sys
import json
import time
import random
import os
from urllib.parse import urlparse

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel,
    QPushButton, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt5.QtCore import Qt, pyqtSignal, QThread
from PyQt5.QtGui import QColor

from PyQt5.QtGui import QPixmap
from urllib.request import urlopen

from selenium.webdriver.support.ui import WebDriverWait

from urllib.parse import urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


# ===================== CONFIG =====================
COOKIE_FILE = "cookies.json"
MAX_RUNTIME_MINUTES = 20
DELAY_MIN = 5
DELAY_MAX = 10
HEADLESS = True
SCROLL_PAUSE_MIN = 3
SCROLL_PAUSE_MAX = 6

# ===================== GLOBAL =====================
total_actions = 0
stop_requested = False
worker_instance = None


# ===================== DRIVER =====================
def setup_driver():
    options = Options()
    if HEADLESS:
        options.add_argument("--headless=new")

    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
    )

    return driver


# ===================== LOGIN =====================
def load_cookies(driver):
    global worker_instance

    if not os.path.exists(COOKIE_FILE):
        if worker_instance:
            worker_instance.log_signal.emit("cookies.json tidak ditemukan")
        return False

    driver.get("https://www.facebook.com/")
    time.sleep(3)

    with open(COOKIE_FILE, "r") as f:
        cookies = json.load(f)

    for c in cookies:
        try:
            driver.add_cookie({
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ".facebook.com"),
                "path": c.get("path", "/")
            })
        except:
            pass

    driver.get("https://www.facebook.com/")
    time.sleep(5)

    if "login" in driver.current_url.lower():
        if worker_instance:
            worker_instance.log_signal.emit("Cookie invalid")
        return False

    if worker_instance:
        worker_instance.log_signal.emit("Login sukses")

    return True


# ===================== UTILS =====================
def fast_pause():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def safe_click(driver, element, retry=3):
    for _ in range(retry):
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});",
                element
            )
            time.sleep(1)
            driver.execute_script("arguments[0].click();", element)
            return True
        except:
            time.sleep(1)
    return False

def get_user_info_from_button(btn):
    try:
        parent = btn
        post = None

        # Naik ke parent sampai menemukan container post
        for _ in range(10):
            parent = parent.find_element(By.XPATH, "..")
            links = parent.find_elements(By.XPATH, ".//a[@href]")
            if len(links) > 5:
                post = parent
                break

        if not post:
            return "Unknown"

        # Cari nama di header post
        header_links = post.find_elements(
            By.XPATH,
            ".//h2//a[@href] | .//strong//a[@href] | .//span//a[@href]"
        )

        for link in header_links:
            name = link.text.strip()
            href = link.get_attribute("href")
            if name and href and "facebook.com" in href:
                return name

        # Fallback ambil dari aria-label tombol
        aria = btn.get_attribute("aria-label")
        if aria:
            return aria.strip()

    except:
        pass

    return "Unknown"
    
    
def check_identity(driver, timeout=15):
    """
    Mengambil:
    - Profile Name
    - Profile ID / Username
    - Avatar URL aktif
    Return: (name, id, avatar_url) atau None
    """

    

    try:
        driver.get("https://www.facebook.com/me")

        wait = WebDriverWait(driver, timeout)

        # Tunggu redirect selesai
        wait.until(lambda d: "facebook.com" in d.current_url)

        current_url = driver.current_url.lower()

        # Jika masih login/checkpoint berarti gagal
        if "login" in current_url or "checkpoint" in current_url:
            return None

        # ========================
        # Ambil Profile ID
        # ========================
        parsed = urlparse(driver.current_url)

        if "profile.php" in parsed.path:
            qs = parse_qs(parsed.query)
            profile_id = qs.get("id", ["unknown"])[0]
        else:
            profile_id = parsed.path.strip("/")

        # ========================
        # Ambil Nama Profile
        # ========================
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        profile_name = driver.find_element(By.TAG_NAME, "h1").text.strip()

        if not profile_name:
            profile_name = "Unknown"

        # ========================
        # Ambil Avatar (METODE 1 - paling stabil)
        # ========================
        avatar_url = None

        try:
            img = driver.find_element(
                By.XPATH,
                "//img[contains(@alt,'profile picture') or contains(@alt,'Foto Profil')]"
            )
            avatar_url = img.get_attribute("src")
        except:
            pass

        # ========================
        # METODE 2 - fallback SVG
        # ========================
        if not avatar_url:
            try:
                img = driver.find_element(
                    By.XPATH,
                    "//svg//image[contains(@xlink:href,'scontent')]"
                )
                avatar_url = img.get_attribute("xlink:href")
            except:
                pass

        # ========================
        # METODE 3 - fallback generic
        # ========================
        if not avatar_url:
            images = driver.find_elements(By.XPATH, "//img[contains(@src,'scontent')]")
            if images:
                avatar_url = images[0].get_attribute("src")

        return profile_name, profile_id, avatar_url

    except Exception as e:
        print("Identity Error:", e)
        return None
    
# ===================== RESULT =====================
def print_result(action, name, status):
    global total_actions, worker_instance

    total_actions += 1

    if worker_instance:
        worker_instance.result_signal.emit(action, name, status)
        worker_instance.counter_signal.emit(total_actions)


# ===================== LIKE =====================
def like_all_visible(driver):
    buttons = driver.find_elements(
        By.XPATH,
        "//div[@role='button'][.//span[text()='Suka'] or .//span[text()='Like']]"
    )

    for btn in buttons:
        if stop_requested:
            return

        try:
            aria = (btn.get_attribute("aria-label") or "").lower()
            if "hapus suka" in aria or "remove like" in aria:
                continue

            if safe_click(driver, btn):
                user_name = get_user_info_from_button(btn)
                print_result("LIKE", user_name, "OK")
                fast_pause()

        except:
            continue


# ===================== WORKER =====================
class BotWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    counter_signal = pyqtSignal(int)
    status_signal = pyqtSignal(str)
    result_signal = pyqtSignal(str, str, str)
    identity_signal = pyqtSignal(str, str, str)

    def run(self):
        global stop_requested, total_actions, worker_instance

        worker_instance = self
        stop_requested = False
        total_actions = 0

        self.status_signal.emit("RUNNING")
        self.log_signal.emit("Bot started")

        driver = setup_driver()

        if not load_cookies(driver):
            self.status_signal.emit("STOPPED")
            return

        identity = check_identity(driver)

        if not identity:
            self.log_signal.emit("❌ Identity check gagal")
            self.status_signal.emit("STOPPED")
            driver.quit()
            return

        profile_name, profile_id, avatar = identity
        
        self.identity_signal.emit(profile_name, profile_id, avatar)
        self.log_signal.emit("✅ Identity Verified")
        
        
        driver.get("https://www.facebook.com/")
        time.sleep(6)

        start_time = time.time()

        while not stop_requested:
            elapsed = time.time() - start_time
            progress = int((elapsed / (MAX_RUNTIME_MINUTES * 60)) * 100)
            self.progress_signal.emit(min(progress, 100))

            if elapsed > MAX_RUNTIME_MINUTES * 60:
                self.log_signal.emit("Runtime selesai")
                break

            like_all_visible(driver)
            time.sleep(random.uniform(4, 7))

        driver.quit()

        self.progress_signal.emit(100)
        self.status_signal.emit("STOPPED")
        self.log_signal.emit("Bot stopped")


# ===================== GUI =====================
class BotGUI(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("🔥 Facebook Auto Like")
        self.setGeometry(300, 200, 1000, 650)

        layout = QVBoxLayout()
        
        self.identity_label = QLabel("Logged as: -")
        self.identity_label.setAlignment(Qt.AlignCenter)
        self.identity_label.setStyleSheet("""
    background-color: #222;
    color: white;
    font-size: 14px;
    padding: 8px;
    border-radius: 8px;
""")
        layout.addWidget(self.identity_label)

        self.avatar_label = QLabel()
        self.avatar_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.avatar_label)


        self.status_label = QLabel("Status: STOPPED")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.status_label)

        self.counter_label = QLabel("Total Actions: 0")
        self.counter_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.counter_label)

        self.progress = QProgressBar()
        layout.addWidget(self.progress)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(
            ["No", "Action", "Name", "Status"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        self.start_btn = QPushButton("▶ START")
        self.stop_btn = QPushButton("⛔ STOP")
        layout.addWidget(self.start_btn)
        layout.addWidget(self.stop_btn)

        self.setLayout(layout)

        self.worker = BotWorker()

        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.counter_signal.connect(self.update_counter)
        self.worker.status_signal.connect(self.update_status)
        self.worker.result_signal.connect(self.add_table_row)

        self.start_btn.clicked.connect(self.start_bot)
        self.stop_btn.clicked.connect(self.stop_bot)
        self.worker.log_signal.connect(self.print_log)
        self.worker.identity_signal.connect(self.update_identity)

    def start_bot(self):
        global stop_requested

        if not self.worker.isRunning():
            stop_requested = False
            self.progress.setValue(0)
            self.table.setRowCount(0)
            self.counter_label.setText("Total Actions: 0")
            self.worker.start()

    def stop_bot(self):
        global stop_requested
        stop_requested = True

    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")
        if status == "RUNNING":
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.status_label.setStyleSheet("color: red; font-weight: bold;")

    def update_counter(self, value):
        self.counter_label.setText(f"Total Actions: {value}")

    def add_table_row(self, action, name, status):
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table.setItem(row, 1, QTableWidgetItem(action))
        self.table.setItem(row, 2, QTableWidgetItem(name))

        status_item = QTableWidgetItem(status)
        status_item.setTextAlignment(Qt.AlignCenter)

        if status == "OK":
            status_item.setForeground(QColor("green"))
        elif status == "SKIP":
            status_item.setForeground(QColor("orange"))
        elif status == "FAIL":
            status_item.setForeground(QColor("red"))

        self.table.setItem(row, 3, status_item)
        self.table.scrollToBottom()

    def print_log(self, message):
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.table.setItem(row, 1, QTableWidgetItem("SYSTEM"))
        self.table.setItem(row, 2, QTableWidgetItem(message))
        self.table.setItem(row, 3, QTableWidgetItem("INFO"))

        self.table.scrollToBottom()
        
        
    def update_identity(self, name, profile_id, avatar_url):
        from PyQt5.QtGui import (
            QPainter, QPainterPath, QPen,
            QColor, QPixmap
        )
        from PyQt5.QtWidgets import (
            QGraphicsDropShadowEffect,
            QGraphicsOpacityEffect
        )
        from PyQt5.QtCore import (
            QPropertyAnimation,
            QEasingCurve,
            Qt
        )
        from urllib.request import urlopen

        # ==========================
        # Update Identity Label
        # ==========================
        self.identity_label.setText(f"🟢 Logged as: {name} ({profile_id})")
        self.identity_label.setStyleSheet("""
            background-color: #1f6f3f;
            color: white;
            font-weight: bold;
            font-size: 14px;
            padding: 8px;
            border-radius: 8px;
        """)

        if not avatar_url:
            return

        try:
            # Load HD Avatar
            data = urlopen(avatar_url).read()
            original = QPixmap()
            original.loadFromData(data)

            size = 130
            glow_color = QColor(0, 255, 120)

            scaled = original.scaled(
                size,
                size,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )

            # Create Circular Avatar
            avatar = QPixmap(size, size)
            avatar.fill(Qt.transparent)

            painter = QPainter(avatar)
            painter.setRenderHint(QPainter.Antialiasing)

            path = QPainterPath()
            path.addEllipse(0, 0, size, size)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled)

            # Glow Border
            painter.setClipping(False)
            pen = QPen(glow_color, 4)
            painter.setPen(pen)
            painter.drawEllipse(2, 2, size - 4, size - 4)

            # Online Indicator
            online_size = 22
            painter.setBrush(QColor(0, 255, 0))
            painter.setPen(QPen(Qt.white, 3))
            painter.drawEllipse(
                size - online_size,
                size - online_size,
                online_size,
                online_size
            )

            painter.end()

            # Set Avatar
            self.avatar_label.setFixedSize(size, size)
            self.avatar_label.setPixmap(avatar)

            # Shadow Effect
            shadow = QGraphicsDropShadowEffect(self.avatar_label)
            shadow.setBlurRadius(35)
            shadow.setOffset(0, 0)
            shadow.setColor(glow_color)
            self.avatar_label.setGraphicsEffect(shadow)

            # Fade-In Animation
            opacity = QGraphicsOpacityEffect(self.avatar_label)
            self.avatar_label.setGraphicsEffect(opacity)

            self.fade_anim = QPropertyAnimation(opacity, b"opacity")
            self.fade_anim.setDuration(800)
            self.fade_anim.setStartValue(0)
            self.fade_anim.setEndValue(1)
            self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
            self.fade_anim.start()

        except Exception as e:
            print("Avatar UI Error:", e)      
# ===================== MAIN =====================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BotGUI()
    window.show()
    sys.exit(app.exec_())
