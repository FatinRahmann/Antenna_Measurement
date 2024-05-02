from RsInstrument.RsInstrument import RsInstrument
from pipython import GCSDevice, pitools
import tkinter as tk
import numpy as np
import math
import matplotlib.pyplot as plt
from datetime import date

restart_window = None
instr = None

#Connection with Vector Network Analyser/Analyseur Du Reseau
try:
    instr = RsInstrument('TCPIP::169.254.202.203::INSTR', True, True)
    instr.visa_timeout = 10000
    instr.opc_timeout = 100000
    instr.instrument_status_checking = True
    instr.opc_query_after_write = True

except Exception as ex:
    print('Error initializing the instrument session:\n' + ex.args[0])
    exit()

def close_program():
    app.destroy()
    instr.close() #Close connection with VNA
    gcs.close() #Close connection with motor

def show_restart_window():
    global restart_window  

    restart_window = tk.Toplevel()
    restart_window.title('Restart measurement')
    restart_window.geometry('300x200')
    label = tk.Label(restart_window, text='Restart measure?')
    label.pack(padx=10, pady=10)

    restart_button = tk.Button(restart_window, text='Restart', command=restart_app)
    restart_button.pack(padx=10, pady=10)

    no_button = tk.Button(restart_window, text='No', command=close_program)
    no_button.pack(padx=10, pady=10)

def config_VNA():
    print(f'Driver Version: {instr.driver_version}')
    print(f'SpecAn IDN: {instr.idn_string}')
    print(f'visa_manufacturer: {instr.visa_manufacturer}')
    print(f'full_instrument_model_name: {instr.full_instrument_model_name}')
    print(f'instrument_serial_number: {instr.instrument_serial_number}')
    print(f'firmware_version: {instr.instrument_firmware_version}')
    print(f'instrument_options: List: {instr.instrument_options}')
    print(f'opc_timeout: {instr.opc_timeout}')
    print(f'visa_timeout: {instr.visa_timeout}')
    print(f'SpecAn Options: {",".join(instr.instrument_options)}')

    freq_start = float(frequence_start_entry.get())
    freq_stop = float(frequence_stop_entry.get())
    freq_points = float(frequence_points_entry.get())

    print('=====================================')
    print('============= Configuration of the VNA')
    print('=====================================')

    instr.clear_status()  # Clean all subsystem instrument errors
    instr.write_str('*RST')
    instr.write_str(f'FREQ:STARt {freq_start} GHZ')
    instr.write_str(f'FREQ:STOP {freq_stop} GHZ')
    instr.write_str('BAND 1 kHz')  # RBW
    instr.write_str('DISP:WIND:TRAC:Y:RLEV 0.0')  # Reference Level
    instr.write_str('SYSTEM:DISPLAY:UPDATE ON')

    print('\n VNA Configured !\n')

    instr.write_str('DISPLAY:WINDOW1:TRACE1:DELETE')
    instr.write_str('SOURce1:PATH1:DIRectaccess B16')
    instr.write_str('SOURce1:PATH2:DIRectaccess B16')
    instr.write_str('DISP:WIND1:STAT ON')
    instr.write_str(f'SWE:POIN {freq_points}')  # Sweep points

    # ====== "Ch1Tr1" Configuration // probe 1
    instr.write_str('CALC1:PAR:SDEF "Ch1Tr1", "B2/A1D1"')  # Choose the ratio b2/a1 Port 1
    instr.write_str('CALC1:FORM  MLOGarithmic; :DISP:WIND1:TRAC2:FEED "Ch1Tr1"')

    # ===== "Ch1Tr2" Configuration // probe 2
    instr.write_str('CALC2:PAR:SDEF "Ch1Tr2","A2/A1D1"')  # Choose the ratio a2/a1 Port 1
    instr.write_str('CALC2:FORM  MLOGarithmic; :DISP:WIND1:TRAC3:FEED "Ch1Tr2"')

def restart_app():
    # Close the restart window
    restart_window.destroy()
    # Re-create the main app window
    app.deiconify()

def start_measurement():
    global gcs
    angle_min = float(angle_min_entry.get())
    angle_max = float(angle_max_entry.get())
    angle_step = float(angle_step_entry.get())
    freq_points = int(frequence_points_entry.get())
    offset = float(offset_entry.get())
    current_angle = angle_min
    middle = 0  # (freq_points * 2) - 1

    #  Connection to the stepper motor controller
    gcs = GCSDevice('C-863.12')
    print("Connecting GCS")
    gcs_sn = "021550330" # Since we know the serial number of the device we can connect to it using this method
    # gcs.InterfaceSetupDlg() # If we don't know which device to connect to we can show a dialog window to select it
    gcs.ConnectUSB(gcs_sn)
    print('GCS connected: {}'.format(gcs.qIDN().strip()))
    axis = 1 # Used by the PI motor, we have only one dimension(axis): rotation


    #  Create a 1D array with the list of all the angle to take a measurement
    angles_list = np.arange(angle_min, angle_max + 1, angle_step)
    nb_points = len(angles_list)
    print("Total number of points:", nb_points)

    gcs.SVO(axis, 1)  # Set servo ON
    gcs.GOH()  # Go to the home position
    pitools.waitontarget(gcs, axis)
    print("Homing complete !")

    gcs.MOV(axis, angle_min)  # Begin measurement at angle_min position
    pitools.waitontarget(gcs, axis)
    print("Initial position Complete !")

    #  Create 2 multidimensional arrays to store the measurements data
    data_polar_1 = np.zeros(len(angles_list) * 2)
    data_polar_2 = np.zeros(len(angles_list) * 2)

    # Calculation
    # Create multidimensional arrays to store the results of the calculations for each measured port
    amplitude_polar_1 = np.zeros(len(angles_list))
    amplitude_polar_2 = np.zeros(len(angles_list))
    total_gain = np.zeros(len(angles_list))

    #Function for autoscale of y-axis 
    def autoscale_y(ax, margin=0.1):
        def get_bottom_top(line):
            xd = line.get_xdata()
            yd = line.get_ydata()
            lo, hi = ax.get_xlim()
            y_displayed = yd[((xd > lo) & (xd < hi))]
            h = np.max(y_displayed) - np.min(y_displayed)
            bot = np.min(y_displayed) - margin * h
            top = np.max(y_displayed) + margin * h
            return bot, top

        lines = ax.get_lines()
        bot, top = np.inf, -np.inf

        for line in lines:
            new_bot, new_top = get_bottom_top(line)
            if new_bot < bot: bot = new_bot
            if new_top > top: top = new_top

        ax.set_ylim(bot, top)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    zeros_y_axis = np.zeros((len(angles_list), 1))
    line1, = ax.plot(angles_list, zeros_y_axis, label='Total Gain', lw=1)
    line2, = ax.plot(angles_list, zeros_y_axis, label='Amplitude Polar 1', lw=1)
    line3, = ax.plot(angles_list, zeros_y_axis, label='Amplitude Polar 2', lw=1)
    fig.canvas.draw()
    fig.canvas.flush_events()
    plt.ylim((-10, 20))
    plt.title('Total Gain')
    plt.xlabel('Phi (degree)')
    plt.ylabel('Mag (dB)')
    plt.legend(loc='best')
    plt.grid()
    plt.draw()
    plt.ion()
    plt.show()

    for i in range(len(angles_list)):
        print("Measure...")
        # Trace 1
        instr.write_str(':CALCULATE1:PARAMETER:SELECT "Ch1Tr1"')
        temp = instr.query_bin_or_ascii_float_list('FORM ASCII; :TRAC? CH1DATA')
        data_polar_1[i] = temp[middle]  # Re
        data_polar_1[i + 1] = temp[middle + 1]  # Im

        # Trace 2
        instr.write_str(':CALCULATE2:PARAMETER:SELECT "Ch1Tr2"')
        temp = instr.query_bin_or_ascii_float_list('FORM ASCII; :TRAC? CH2DATA')
        data_polar_2[i] = temp[middle]  # Re
        data_polar_2[i + 1] = temp[middle + 1]  # Im

        # Calculate Re and Im
        temp1_Re = data_polar_1[i]
        temp1_Im = data_polar_1[i + 1]
        temp2_Re = data_polar_2[i]
        temp2_Im = data_polar_2[i + 1]

        amplitude_polar_1[i] = 10 * math.log10((temp1_Re ** 2) + (temp1_Im ** 2)) - offset
        amplitude_polar_2[i] = 10 * math.log10((temp2_Re ** 2) + (temp2_Im ** 2)) - offset
        total_gain[i] = 10 * math.log10(
            ((temp2_Re ** 2 + temp1_Re ** 2) + (temp2_Im ** 2 + temp1_Im ** 2))) - offset

        # Plot graph gain in function of angles
        s1 = total_gain[:]
        line1.set_ydata(s1)

        amplitude_polar_c1 = amplitude_polar_1[:]
        line2.set_ydata(amplitude_polar_c1)

        amplitude_polar_c2 = amplitude_polar_2[:]
        line3.set_ydata(amplitude_polar_c2)

        fig.canvas.draw()
        fig.canvas.flush_events()

        # Autoscale y-axis
        autoscale_y(ax)

        # Preparing for next measurement
        print(f'Changing angle {i}/{len(angles_list)}, {(i / len(angles_list) * 100):.0f} %')
        print(f'Angle is {current_angle}')
        gcs.MVR(axis, angle_step)  # Move to the next angle
        current_angle = current_angle + angle_step
        pitools.waitontarget(gcs, axis)

    print('Return to home')
    gcs.GOH()
    pitools.waitontarget(gcs, axis)

    gcs.close()

    plt.ioff()
    plt.grid()
    plt.show()


    # Download results
    path = "measurements/" #Create and insert your own desired path
    date_test = date.today()
    formatted_date = date_test.strftime('%Y%m%d')
    filename = path + formatted_date + '_' + str(angle_min) + '_' + str(angle_max) + '_' + str(angle_step)
    np.savetxt(filename + '_DATA_polar_1' + '.csv', amplitude_polar_1[:], delimiter=';')
    np.savetxt(filename + '_DATA_polar_2' + '.csv', amplitude_polar_2[:], delimiter=';')
    np.savetxt(filename + '_DATA_Total_Gain' + '.csv', total_gain[:], delimiter=';')
    np.savetxt(filename + '_DATA_angle_list.csv', angles_list, delimiter=';')
    np.savetxt(filename + '_temp.csv', temp, delimiter=';')

    path_png = filename + '_plot.png'
    fig.savefig(path_png)
    
    show_restart_window()

app = tk.Tk()
app.title("Mesure d'antenne GUI")
app.geometry('480x380')

# CONFIG VNA
left_frame_middle = tk.Frame(app, height=170, width=100, bg='light grey')
left_frame_middle.grid(row=0, column=0, pady=10, padx=10)

frequence_start_label = tk.Label(left_frame_middle, text='Frequence start (GHz)')
frequence_start_label.grid(row=1, column=0, pady=5, padx=5)
frequence_start_entry = tk.Entry(left_frame_middle)
frequence_start_entry.insert(index=0, string="27")  # default value
frequence_start_entry.grid(row=1, column=1, pady=5, padx=5)

frequence_stop_label = tk.Label(left_frame_middle, text='Frequence stop (GHz)')
frequence_stop_label.grid(row=2, column=0, pady=5, padx=5)
frequence_stop_entry = tk.Entry(left_frame_middle)
frequence_stop_entry.insert(index=0, string="30")  # default value
frequence_stop_entry.grid(row=2, column=1, pady=5, padx=5)

frequence_points_label = tk.Label(left_frame_middle, text='Frequence points')
frequence_points_label.grid(row=3, column=0, pady=5, padx=5)
frequence_points_entry = tk.Entry(left_frame_middle)
frequence_points_entry.insert(index=0, string="3")  # default value
frequence_points_entry.grid(row=3, column=1, pady=5, padx=5)

configure_vna = tk.Button(left_frame_middle, text='Configure VNA', command=config_VNA)
configure_vna.grid(row=4, column=0, pady=5, padx=5)

# MESURE
right_frame_top = tk.Frame(app, height=170, width=100, bg='light grey')
right_frame_top.grid(row=3, column=0, pady=10, padx=10)

angle_min_label = tk.Label(right_frame_top, text='Angle min (deg)')
angle_min_label.grid(row=1, column=0, pady=5, padx=5)
angle_min_entry = tk.Entry(right_frame_top)
angle_min_entry.insert(index=0, string="-40")  # default value
angle_min_entry.grid(row=1, column=1, pady=5, padx=5)

angle_max_label = tk.Label(right_frame_top, text='Angle max (deg)')
angle_max_label.grid(row=2, column=0, pady=5, padx=5)
angle_max_entry = tk.Entry(right_frame_top)
angle_max_entry.insert(index=0, string="40")  # default value
angle_max_entry.grid(row=2, column=1, pady=5, padx=5)

angle_step_label = tk.Label(right_frame_top, text='Angle step')
angle_step_label.grid(row=3, column=0, pady=5, padx=5)
angle_step_entry = tk.Entry(right_frame_top)
angle_step_entry.insert(index=0, string="2")  # default value
angle_step_entry.grid(row=3, column=1, pady=5, padx=5)

offset_label = tk.Label(right_frame_top, text='Offset')
offset_label.grid(row=4, column=0, pady=5, padx=5)
offset_entry = tk.Entry(right_frame_top)
offset_entry.insert(index=0, string="-40")  # default value
offset_entry.grid(row=4, column=1, pady=5, padx=5)

measure_button = tk.Button(right_frame_top, text='Start measure', command=start_measurement)
measure_button.grid(row=5, column=0, pady=5, padx=5)

close_button = tk.Button(app, text='Close', command=close_program)
close_button.place(relx=1.0, rely=1.0, anchor='se', bordermode='outside', x=-10, y=-10)

app.mainloop()
