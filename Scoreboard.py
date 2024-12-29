import sys
import serial
import threading
from PyQt5.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

class QuantumReader(threading.Thread):
    def __init__(self, port, baudrate, callback):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.callback = callback
        self.running = True
        self.serial_connection = None

    def run(self):
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )

            while self.running:
                if self.serial_connection.in_waiting > 0:
                    data = self.serial_connection.readline().decode('utf-8').strip()
                    self.callback(data)

        except serial.SerialException as e:
            print(f"Serial connection error: {e}")

    def stop(self):
        self.running = False
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()

class Scoreboard(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.label = QLabel("Waiting for data...")
        layout = QVBoxLayout()
        layout.addWidget(self.label)
        self.setLayout(layout)
        self.setWindowTitle('Virtual Scoreboard')

    def update_data(self, text):
        self.label.setText(text)

if __name__ == "__main__":
    # Configuration for RS422
    COM_PORT = 'COM1'  # Change to the actual COM port
    BAUD_RATE = 9600

    app = QApplication(sys.argv)
    scoreboard = Scoreboard()


    def handle_data(data):
        print(f"Received: {data}")
        scoreboard.update_data(data)

        # Сохранение данных в лог-файл
        with open("quantum_data_log.txt", "a") as log_file:
            log_file.write(data + "\\n")


    reader = QuantumReader(COM_PORT, BAUD_RATE, handle_data)
    reader.start()

    scoreboard.show()
    try:
        sys.exit(app.exec_())
    finally:
        reader.stop()
