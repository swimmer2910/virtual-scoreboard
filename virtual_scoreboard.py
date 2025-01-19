import re
import serial
import tkinter as tk
from tkinter import font
import threading


class VirtualScoreboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Virtual Scoreboard")

        # Customize the font
        self.custom_font = font.Font(family="Helvetica", size=36, weight="bold")

        # Create labels for the scoreboard
        self.period_time_label = tk.Label(root, text="Period Time: N/A", font=self.custom_font)
        self.home_score_label = tk.Label(root, text="Home Score: N/A", font=self.custom_font)
        self.visitors_score_label = tk.Label(root, text="Visitors Score: N/A", font=self.custom_font)
        self.date_label = tk.Label(root, text="Date: N/A", font=self.custom_font)
        self.time_label = tk.Label(root, text="Time: N/A", font=self.custom_font)
        self.timeout_label = tk.Label(root, text="", font=self.custom_font, fg="red")

        # Arrange the labels in the window
        self.period_time_label.pack(pady=10)
        self.home_score_label.pack(pady=10)
        self.visitors_score_label.pack(pady=10)
        self.date_label.pack(pady=10)
        self.time_label.pack(pady=10)
        self.timeout_label.pack(pady=10)

        # Initialize state
        self.is_timeout = False
        self.timeout_seconds = 0
        self.timeout_delay_counter = 0

    def update_scoreboard(self, data):
        # Update the scores and other data
        self.home_score_label.config(text=f"Home: {data['home_score']}")
        self.visitors_score_label.config(text=f"Visitors: {data['visitors_score']}")
        self.date_label.config(text=f"Date: {data['date']}")
        self.time_label.config(text=f"Time: {data['time']}")

        # Update the period or timeout display
        if self.is_timeout:
            self.timeout_label.config(text=f"Timeout: {data['timeout_seconds']} seconds")
            self.period_time_label.config(text="")
        else:
            self.period_time_label.config(text=f"Period Time: {data['period_time']}")
            self.timeout_label.config(text="")

        self.root.update()

    def start_timeout(self, seconds):
        self.is_timeout = True
        self.timeout_seconds = seconds
        self.timeout_delay_counter = 0

    def check_timeout(self, data):
        if 'timeout_seconds' in data:
            self.timeout_delay_counter = 0
        else:
            self.timeout_delay_counter += 1
            if self.timeout_delay_counter >= 1:  # Assuming the function is called every second
                self.is_timeout = False


def parse_scoreboard_data(decoded_data, previous_data, scoreboard):
    # Use regular expressions to extract the scoreboard information
    period_time_pattern = re.compile(r'D\s*(\d{1,2}:\d{2})')
    score_pattern = re.compile(r'D\s*\d{1,2}:\d{2}\s+(\d+)\s+(\d+)')
    datetime_pattern = re.compile(r'T(\d{2}/\d{2}/\d{2})(\d{2}:\d{2}\.\d{2})')
    timeout_pattern = re.compile(r'D\s*:(\d{2})')
    timeout_score_pattern = re.compile(r'D\s*:\d{2}\s+(\d+)\s+(\d+)')

    # Initialize data dictionary with previous values
    data = previous_data.copy()

    # Find the matches
    period_time_match = period_time_pattern.search(decoded_data)
    score_match = score_pattern.search(decoded_data)
    datetime_match = datetime_pattern.search(decoded_data)
    timeout_match = timeout_pattern.search(decoded_data)
    timeout_score_match = timeout_score_pattern.search(decoded_data)

    # Extract and update the scores, period time, date, and time based on the current state
    if period_time_match:
        data['period_time'] = period_time_match.group(1)
        data['home_score'] = score_match.group(1)
        data['visitors_score'] = score_match.group(2)
        scoreboard.is_timeout = False
    elif timeout_score_match:
        data['home_score'] = timeout_score_match.group(1)
        data['visitors_score'] = timeout_score_match.group(2)
        if timeout_match:
            data['timeout_seconds'] = int(timeout_match.group(1))
            scoreboard.start_timeout(data['timeout_seconds'])
        else:
            if 'timeout_seconds' in data:
                del data['timeout_seconds']

    if datetime_match:
        data['date'] = datetime_match.group(1)
        data['time'] = datetime_match.group(2)

    return data


def read_serial_data(port, baudrate, scoreboard):
    # Open the serial port
    ser = serial.Serial(port, baudrate)

    # Initialize previous data
    previous_data = {
        'period_time': 'N/A',
        'home_score': 'N/A',
        'visitors_score': 'N/A',
        'date': 'N/A',
        'time': 'N/A'
    }

    try:
        while True:
            # Read a chunk of data from the serial port
            data = ser.read(ser.in_waiting or 1)

            if data:
                # Attempt to decode the data using 'latin1' encoding
                decoded_data = data.decode('latin1', errors='ignore')
                print("Decoded Data:", decoded_data)

                # Parse the decoded data
                parsed_data = parse_scoreboard_data(decoded_data, previous_data, scoreboard)

                # Update the previous data
                previous_data = parsed_data

                # Check for timeout marker with delay
                scoreboard.check_timeout(parsed_data)

                # Update the scoreboard
                scoreboard.update_scoreboard(parsed_data)

    except KeyboardInterrupt:
        # Exit the loop on keyboard interrupt
        print("Stopping data collection.")
    finally:
        # Close the serial port
        ser.close()


if __name__ == "__main__":
    port = 'COM9'  # Replace with your serial port
    baudrate = 9600

    # Create the main window
    root = tk.Tk()
    scoreboard = VirtualScoreboard(root)

    # Start reading and parsing data from the serial port in real time
    threading.Thread(target=read_serial_data, args=(port, baudrate, scoreboard)).start()

    # Run the Tkinter main loop
    root.mainloop()