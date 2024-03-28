# !/usr/bin/python3
import tkinter
import tkinter.font as tkFont
from tkinter.messagebox import showerror, showinfo, showwarning
from tkinter.filedialog import askopenfilename, asksaveasfilename
from tkinter.simpledialog import askstring
from tkinter import ttk

import cv2
import PIL.Image, PIL.ImageTk
import numpy as np
from scipy.signal import savgol_filter
import peakutils

from time import sleep
from threading import Thread, Event

from os.path import exists, join
from os import getcwd

from math import log




# https://solarianprogrammer.com/2018/04/21/python-opencv-show-video-tkinter-window/
class App:
    DEFAULT_CALIBRATION = ((405, 532), (152, 276))
    # PiC ((405, 532), (152, 276))
    # IMX ((405, 532), (65, 176))

    def __init__(self, window_title, video_source="WiFi"):
        self.window = tkinter.Tk()
        
        self.window.geometry("1000x500")
        self.window.resizable (width = True, height = True)
        self.window.title(window_title)
        self.def_font = tkinter.font.nametofont("TkDefaultFont")
        self.def_font.config(size=9)

        self.probes = []

        self.graph = Graph(self.DEFAULT_CALIBRATION)

        self.visualise_calibration = False

        # Specify Grid
        tkinter.Grid.rowconfigure(self.window,0,weight=1)
        tkinter.Grid.columnconfigure(self.window,0,weight=1)
        tkinter.Grid.rowconfigure(self.window,1,weight=1)

        self.control_frame = tkinter.Frame(self.window)
        self.control_frame.pack(side="top", fill="x", expand=True)


        # CAMERA
        self.sensor_frame = tkinter.Frame(self.control_frame, highlightbackground="DeepSkyBlue2", highlightthickness="2")
        self.sensor_frame.grid(row=0, column=0, sticky="NSW")
        
        # Source selection
        tkinter.Label(self.sensor_frame, text="Zdroj:", ).grid(row=0, column=0, sticky="E")
        
        self.video_source_dropdown = ttk.Combobox(self.sensor_frame, values=("WiFi", "HW0", "HW1", "HW2", "HW3", "HW4", "HW5"), width=5, state="readonly")
        self.video_source_dropdown.set(video_source)
        self.video_source_dropdown.bind("<<ComboboxSelected>>", self.set_video_source)
        self.video_source_dropdown.grid(row=0, column=1)

        self.exposure_progressbar = ttk.Progressbar(self.sensor_frame, orient='horizontal',mode='determinate')
        self.exposure_progressbar.grid(row=0, column=2, columnspan=2)

        self.graph_update_event = Event()  # event for graph to update after new frame received from cam


        # cam preview button
        tkinter.Button(self.sensor_frame, text="Konfigurovat výši senzoru 📷", command=self.cam_popup, bg="DeepSkyBlue2").grid(row=1,column=0, columnspan=4, sticky="WE")


        # Exposure
        tkinter.Label(self.sensor_frame, text="N Skenů na průměrování:", ).grid(row=2, column=0, columnspan=3, sticky="E")
        self.exposure_spinbox = tkinter.Spinbox(self.sensor_frame, from_=1, to=1000, wrap=False, width=7)
        self.exposure_spinbox.grid(row=2, column=3)


        # CALIBRATION
        self.calibration_frame = tkinter.Frame(self.control_frame, highlightbackground="medium violet red", highlightthickness=2)
        self.calibration_frame.grid(row=0, column=1, sticky="N")

        # wavelength labels
        tkinter.Label(self.calibration_frame, text = "Vlnová délka 1:").grid(row = 0, column = 0, sticky="EW")
        tkinter.Label(self.calibration_frame, text = "Vlnová délka 2:").grid(row = 1, column = 0, sticky="EW")
        # wavelength spinboxes
        self.cal_wavelength1 = tkinter.IntVar(value=0)
        self.cal_wavelength2 = tkinter.IntVar(value=0)
        cal_wavelength1_spinbox = tkinter.Spinbox(self.calibration_frame, from_=0, to=10000, textvariable=self.cal_wavelength1, wrap=False, width=5)
        cal_wavelength1_spinbox.grid(row = 0,column = 1,sticky='E')
        cal_wavelength2_spinbox = tkinter.Spinbox(self.calibration_frame, from_=0, to=10000, textvariable=self.cal_wavelength2, wrap=False, width=5)
        cal_wavelength2_spinbox.grid(row = 1,column = 1,sticky='E')
        
        # calibration point selection
        self.cal_px1 = tkinter.DoubleVar(value=0)
        self.cal_px2 = tkinter.DoubleVar(value=0)
        # point select buttons
        def p1_bind_selection():
            p2_unbind_selection()
            cal_visualise()
            self.graph_canvas.bind("<Button-1>", p1_select)
            self.window.bind("<Escape>", p1_unbind_selection)
            self.cal_p1_select_button.config(text="x",bg="yellow", command=p1_unbind_selection)
        def p1_unbind_selection():
            self.graph_canvas.unbind("<Button-1>")
            self.window.unbind("<Escape>")
            self.cal_p1_select_button.config(text="v",bg="white", command=p1_bind_selection)
            cal_unvisualise()
        def p1_select(event):
            selected_px = round((self.graph.plotx_to_nm(int(event.x))-self.graph.data_nm_min) / self.graph.data_nm_range * self.graph.sensor_width)
            print(self.graph.calibrated_reverse)
            #if self.graph.calibrated_reverse:
            #    selected_px = self.graph.data_nm_range-selected_px
            if selected_px < 0:
                self.cal_px1.set(0)
            elif selected_px > self.graph.sensor_width:
                self.cal_px1.set(self.graph.sensor_width)
            else:
                self.cal_px1.set(selected_px)
            p1_unbind_selection()
            cal_visualise()
            #self.graph_canvas.after(3000, cal_unvisualise)


        self.cal_p1_select_button = tkinter.Button(self.calibration_frame, text="v", bg="white", command=p1_bind_selection)
        self.cal_p1_select_button.grid(row=0, column=2, sticky="W")

        def p2_bind_selection():
            p1_unbind_selection()
            cal_visualise()
            self.graph_canvas.bind("<Button-1>", p2_select)
            self.window.bind("<Escape>", p2_unbind_selection)
            self.cal_p2_select_button.config(text="x",bg="yellow", command=p2_unbind_selection)
        def p2_unbind_selection():
            self.graph_canvas.unbind("<Button-1>")
            self.window.unbind("<Escape>")
            self.cal_p2_select_button.config(text="v",bg="white", command=p2_bind_selection)
            cal_unvisualise()
        def p2_select(event):
            selected_px = round((self.graph.plotx_to_nm(int(event.x))-self.graph.data_nm_min) / self.graph.data_nm_range * self.graph.sensor_width)
            if self.graph.calibrated_reverse:
                selected_px = self.graph.data_nm_range-selected_px
            if selected_px < self.graph.data_nm_min:
                self.cal_px2.set(self.graph.data_nm_min)
            elif selected_px > self.graph.data_nm_min+self.graph.data_nm_range:
                self.cal_px2.set(self.graph.data_nm_min+self.graph.data_nm_range)
            else:
                self.cal_px2.set(selected_px)
            p2_unbind_selection()
            cal_visualise()
            #self.graph_canvas.after(3000, cal_unvisualise)


        self.cal_p2_select_button = tkinter.Button(self.calibration_frame, text="v", bg="white", command=p2_bind_selection)
        self.cal_p2_select_button.grid(row=1, column=2, sticky="W")
        
        def cal_visualise(*_):
            self.visualise_calibration = True
        def cal_unvisualise(*_):
            self.visualise_calibration = False

        # point spinboxes
        cal_p1_spinbox = tkinter.Spinbox(self.calibration_frame, from_=0, to=5000, textvariable=self.cal_px1, wrap=True, width=5)
        cal_p1_spinbox.grid(row = 0,column = 3)
        cal_p2_spinbox = tkinter.Spinbox(self.calibration_frame, from_=0, to=5000, textvariable=self.cal_px2, wrap=True, width=5)
        cal_p2_spinbox.grid(row = 1,column = 3)

        # bind calibration visualisation
        for widget in (cal_p1_spinbox, cal_p2_spinbox, self.cal_p1_select_button, self.cal_p2_select_button, cal_wavelength1_spinbox, cal_wavelength2_spinbox):
            widget.bind("<FocusIn>", cal_visualise)
            widget.bind("<FocusOut>", cal_unvisualise)
        
        
        cal_p1_spinbox.bind("<FocusIn>", cal_visualise)
        cal_p1_spinbox.bind("<FocusOut>", cal_unvisualise)
        cal_p2_spinbox.bind("<FocusIn>", cal_visualise)
        cal_p2_spinbox.bind("<FocusOut>", cal_unvisualise)


        # calibrate button
        def calibrate():
            if 0 not in (self.cal_wavelength1.get(), self.cal_wavelength2.get(), self.cal_px1.get(), self.cal_px2.get()):
                self.graph.calibrate((self.cal_wavelength1.get(), self.cal_wavelength2.get()),
                                     (int(self.cal_px1.get() or 0), int(self.cal_px2.get() or 0)))
                self.calibration_button.configure(text="Rekalibrovat", bg="green2",activebackground='yellow')
            else:
                showwarning(message="Zadejte kalibrační hodnoty")

        self.calibration_button = tkinter.Button(self.calibration_frame ,text="Kalibrovat", padx=5, pady=5, bg="medium violet red", activebackground='red', command=calibrate)
        self.calibration_button.grid(row=0,column=4, rowspan=2, sticky="NS")

        # # PEAK HOLD
        # def peakhold():
        #     if self.peakholdbtn.cget("bg") == 'yellow':
        #         self.peakholdbtn.configure(fg="yellow", bg="red",activebackground='red', activeforeground="yellow")
        #         setattr(self.graph,'holdpeaks',True) # set holdpeaks true
        #         self.filt_scale.configure(state="disabled")
        #     else:
        #         self.peakholdbtn.configure(fg="black", bg="yellow",activebackground='yellow', activeforeground="black")
        #         setattr(self.graph,'holdpeaks',False) # set holdpeaks true
        #         self.filt_scale.configure(state="active")
        # self.peakholdbtn = tkinter.Button(self.settings_frame, text="Peak Hold", width=6,fg="black", bg="yellow", activebackground='yellow', command=peakhold)
        # self.peakholdbtn.grid(row=1, column=6, padx=0, pady=0)    



        # MEASURE
        self.measure_frame = tkinter.Frame(self.control_frame, highlightbackground="yellow3", highlightthickness=2)
        self.measure_frame.grid(row=0, column=2, sticky="N")
        def measure_create():
            self.probes.append([tkinter.Toplevel(self.window), tkinter.DoubleVar()])
            tkinter.Label(self.probes[-1][0], text="Vlnová délka (nm):").grid(row=0, column=0)
            tkinter.Spinbox(self.probes[-1][0], from_=0, to=999, increment=1, textvariable=self.probes[-1][1], wrap=True, width=5).grid(row=0, column=1)
            self.probes[-1][0].geometry("300x50")

            self.probes[-1][0].protocol("WM_DELETE_WINDOW", measure_delete)

        tkinter.Button(self.measure_frame, text="Přidat měřidlo", padx=5, pady=5, bg="yellow2", command=measure_create).grid(row=0, column=0, sticky="EW")    

        def measure_delete():
            if len(self.probes):
                self.probes[-1][0].destroy()
                self.probes.pop()
        tkinter.Button(self.measure_frame, text="Odebrat měřidlo", padx=5, pady=5, bg="yellow4", command=measure_delete).grid(row=1, column=0, sticky="EW")    


        # MASKS
        def set_mask():
            self.graph.mask = self.graph.latest_data
        tkinter.Button(self.control_frame, text="Nastavit blank", bg="orange", command=set_mask).grid(row=0, column=5)
        def mask_on():
            self.graph.usemask = True
            self.mask_button.config(text="Mask OFF", bg="white", fg="black", command=mask_off)
        def mask_off():
            self.graph.usemask = False
            self.mask_button.config(text="Mask ON", bg="black", fg="white", command=mask_on)
        self.mask_button = tkinter.Button(self.control_frame)
        self.mask_button.grid(row=0, column=6)
        mask_off()



        # SAVE/SNAPSHOT
        # Snapshot the graph
        def save_csv():
            filename = askopenfilename(filetypes=[("Spectrum files", "*.csv")], defaultextension=".csv")
            name = askstring("Název měření", "Název měření:")

            cv2.imwrite(join("D:\\Nextcloud\\code\\UTesla\\spektrometr\\dokumentace", "spectrum-" + name + ".jpg"), self.graph.generate_graph(self.cam.latest_frame, self.graph_update_event))

            with open(filename, "r") as f:
                columns = f.readlines()

            with open(filename, "w") as f:
                print(columns)
                columns[0] = columns[0][:-1] + name + "(" + self.graph.plot_y_unit + ");"
                for i in range(self.graph.data_nm_range):
                        columns[i+1] = columns[i][:-1] + str(self.graph.latest_data[i]).replace(".", ",") + ";\n"
                
                f.writelines(columns)
        tkinter.Button(self.control_frame, text="Ulož spektrum", padx=5, pady=5, bg="gold2", command=save_csv).grid(row=0, column=8, columnspan=1, sticky="E")
        
        # create new file for saving 
        def create_csv():
            filename = asksaveasfilename(filetypes=[("Spectrum files", "*.csv")], defaultextension=".csv")
            with open(filename, "w") as f:
                f.write("Wavelength (nm);\n")
                for i in range(self.graph.data_nm_range):
                    f.write(str(i)+ ";\n")
        tkinter.Button(self.control_frame, text="Založ nový CSV soubor", padx=5, pady=5, bg="gold3", command=create_csv).grid(row=0, column=9, columnspan=1, sticky="E")
        

        
        # GRAPH
        self.graph_canvas = tkinter.Canvas(self.window, width = 636, height = 255,borderwidth=2,relief="sunken", cursor="tcross")
        self.graph_canvas.pack(padx=0, pady=0, fill="both", expand=True)

        # cursor
        def graph_cursor(event):
            self.cursor_nm.config(text=str(round(self.graph.plotx_to_nm(event.x))) + " nm")
            self.cursor_intensity.config(text=str(round(self.graph.ploty_to_intensity(event.y), 2)) + self.graph.plot_y_unit)

        self.graph_canvas.bind('<Motion>', graph_cursor)
        # scroll
        def graph_scroll(event):
            if event.delta < 0:
                self.graph.plot_nm_min += 2
            elif event.delta > 0 and self.graph.plot_nm_min >= 2:
                self.graph.plot_nm_min -= 2
        self.graph_canvas.bind("<MouseWheel>", graph_scroll)
        # zoom
        def graph_zoom(event):
            if event.delta < 0: 
                self.graph.plot_nm_range += 2
                if self.graph.plot_nm_min >= 2:
                    self.graph.plot_nm_min -= 1
            elif event.delta > 0 and self.graph.plot_nm_range > 100:
                self.graph.plot_nm_range -= 2
                self.graph.plot_nm_min += 1
        self.graph_canvas.bind("<Control-MouseWheel>", graph_zoom)


        ##BOTTOM PANEL
        self.bottom_frame = tkinter.Frame(self.window)
        self.bottom_frame.pack(side="bottom", fill="x", expand=True)

        # INFO
        self.info_frame = tkinter.Frame(self.bottom_frame)
        self.info_frame.grid(row=0, column=0, sticky="NW")

        self.cursor_nm = tkinter.Label(self.info_frame, text="0 nm")
        self.cursor_nm.grid(row=0, column=0)
        self.cursor_intensity = tkinter.Label(self.info_frame, text="0 %")
        self.cursor_intensity.grid(row=1, column=0)


        # SETTINGS PANEL
        self.settings_frame = tkinter.Frame(self.bottom_frame)
        self.settings_frame.grid(row=0, column=1, sticky="NSEW")

        # TODO: peak detection
        # slider for peak width
        # def peakwidth(val):
        #     self.graph.mindist = val # set object value when peakwidth slider moved.
        # self.peakwidth_scale = tkinter.Scale(self.settings_frame,from_=0, to=100, orient="horizontal", showvalue=False, label="Šířka peaků", command=peakwidth)
        # self.peakwidth_scale.grid(row=0, column=0, padx=0, pady=2, sticky="EW")
        # self.peakwidth_scale.set(50)    

        # slider for threshold
        # def peakthresh(val):
        #     self.graph.thresh = val # set object value when threshold slider moved.
        # self.thresh_scale = tkinter.Scale(self.settings_frame, from_=0, to=100, orient="horizontal", showvalue=False, label="Intenzita peaků", command=peakthresh)
        # self.thresh_scale.grid(row=0, column=1, padx=0, pady=2, sticky="EW")
        # self.thresh_scale.set(20)

        # slider for filter
        def savfilter(val):
            self.graph.filter_level = int(val) # set object value when threshold slider moved.
        self.filt_scale = tkinter.Scale(self.settings_frame, from_=0, to=16, orient="horizontal", showvalue=False, label="Filtr", command=savfilter)
        self.filt_scale.grid(row=0, column=2, padx=0, pady=2, sticky="EW")
        self.filt_scale.set(0)

        # APPEARENCE
        self.appearance_frame = tkinter.Frame(self.bottom_frame)
        self.appearance_frame.grid(row=0, column=2, sticky="NSEW")

        # color spectrum toggle
        def color_button_on():
            self.color_button.config(command=color_button_off, text="Odbarvit graf", bg="black", fg="white")
            self.graph.draw_color = True
        def color_button_off():
            self.color_button.config(command=color_button_on, text="Vybarvit graf", bg="red", fg="green2")
            self.graph.draw_color = False
        
        self.color_button = tkinter.Button(self.appearance_frame)
        self.color_button.grid(row=0, column=0)
        color_button_off()

        # granular grid toggle
        def grid_button_on():
            self.grid_button.config(command=grid_button_off, text="podrobná mřížka OFF", bg="gray30")
            self.graph.draw_grid = True
        def grid_button_off():
            self.grid_button.config(command=grid_button_on, text="podrobná mřížka ON", bg="gray60")
            self.graph.draw_grid = False
        
        self.grid_button = tkinter.Button(self.appearance_frame)
        self.grid_button.grid(row=1, column=0)
        grid_button_on()



        # # # # # # # # # # # # # # # # # # # #


        # connect to cam on default source
        self.set_video_source()

        # start graph update loop
        self.update_graph()
        
        self.window.mainloop()

    def set_video_source(self, *args):
        try:
            self.cam = Camera(self.video_source_dropdown.get(), self.graph_update_event)
            self.cal_px1.set(0)
            self.cal_px2.set(0)

            self.video_source_dropdown.config(background="white")
            
        except ValueError:
            showerror("Chyba", "Kamera nenalezana na zdroji: " + str(self.video_source.get() or 0) + ", zadejte jiný zdroj")
            self.video_source_dropdown.config(background="red")

    def cam_popup(self):
        self.cam_window = tkinter.Toplevel(self.window)
        self.cam_window.columnconfigure(0, weight=10)

        #  Create a canvas that can fit the above video source size
        self.cam_canvas = tkinter.Canvas(self.cam_window, width=640, height=480, borderwidth=2, relief="sunken")
        self.cam_canvas.grid(row=0, column=0, padx=(10,0))

        def set_sensor_height(val):
            self.graph.measure_height.set(int(val))

        measure_scale = tkinter.Scale(self.cam_window, from_=1, to=480, orient="vertical", showvalue=False, command=set_sensor_height)
        measure_scale.grid(row=0, column=1, sticky="NS")
        measure_scale.set(self.graph.measure_height.get() or 0)

        tkinter.Spinbox(self.cam_window, from_=0, to=480, width=3, textvariable=self.graph.measure_height, wrap=False).grid(row=1, column=0, columnspan=2, sticky="SE")

        self.update_cam_popup()

    def update_cam_popup(self, delay=15):
        valid_data, frame = self.cam.latest_frame
        frame = cv2.resize(frame, (640, 480)) # resize the live image
        if valid_data:
            cv2.line(frame,(0,int(self.graph.measure_height.get() or 0)),(640,int(self.graph.measure_height.get() or 0)),(255,255,255),1)

            self.window.frame = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame))
            self.cam_canvas.create_image(0, 0, image = self.window.frame, anchor = tkinter.NW)
        
        def cam_close():
            self.cam_window.destroy()
        self.cam_window.protocol("WM_DELETE_WINDOW", cam_close)
        self.cam_window.after(delay, self.update_cam_popup)


    def update_graph(self, delay=100):
        # update graph size if necessary
        if self.graph.graph_width != self.graph_canvas.winfo_width() and self.graph_canvas.winfo_width() != 1:
            self.graph.graph_width = self.graph_canvas.winfo_width()-5
        if self.graph.graph_height != self.graph_canvas.winfo_height() and self.graph_canvas.winfo_height() != 1:
            self.graph.graph_height = self.graph_canvas.winfo_height()-5

        # update exposure
        try:
            assert int(self.exposure_spinbox.get()) >= 1
            self.graph.exposure = int(self.exposure_spinbox.get())
            self.exposure_spinbox.config(bg="white")
        except:
            self.exposure_spinbox.config(bg="red")

        frame = self.graph.generate_graph(self.cam.latest_frame, self.graph_update_event)

        self.exposure_progressbar["value"] = self.graph.exposure_progress / self.graph.exposure * 100

        # calibration lines
        if self.visualise_calibration:
            cv2.line(frame, (self.graph.nm_to_plotx(float(self.cal_px1.get() or 0)  / self.graph.sensor_width * self.graph.data_nm_range + self.graph.data_nm_min),0), (self.graph.nm_to_plotx(float(self.cal_px1.get() or 0)  / self.graph.sensor_width * self.graph.data_nm_range + self.graph.data_nm_min), self.graph_canvas.winfo_height()),(0,0,255),1)
            cv2.line(frame, (self.graph.nm_to_plotx(float(self.cal_px2.get() or 0)  / self.graph.sensor_width * self.graph.data_nm_range + self.graph.data_nm_min),0), (self.graph.nm_to_plotx(float(self.cal_px2.get() or 0)  / self.graph.sensor_width * self.graph.data_nm_range + self.graph.data_nm_min), self.graph_canvas.winfo_height()),(0,0,255),1)

        # update measures
        for i in range(len(self.probes)):
            try:
                cv2.line(frame, (self.graph.nm_to_plotx(float(self.probes[i][1].get() or 0)),0), (self.graph.nm_to_plotx(float(self.probes[i][1].get() or 0)), self.graph.graph_height),(0,255,0),1)
                self.probes[i][0].title(str(self.graph.latest_data[int(self.probes[i][1].get() or 0)-self.graph.data_nm_min]) + self.graph.plot_y_unit)
            except (IndexError, tkinter.TclError):
                self.probes[i][0].title("špatná vlnová délka")
        
        self.window.graph = PIL.ImageTk.PhotoImage(image = PIL.Image.fromarray(frame))
        self.graph_canvas.create_image(0, 0, image = self.window.graph, anchor = tkinter.NW)
        self.window.after(delay, self.update_graph)



class Camera:
    def __init__(self, video_source, update_event):
        self.video_source = video_source
        if self.video_source == "WiFi":
            """ LAN Camera: """
            import imagezmq
            self.image_hub = imagezmq.ImageHub()


        else:
            """ HW Camera:"""
            # Open the video source
            self.vid = cv2.VideoCapture(int(video_source[-1]), cv2.CAP_DSHOW)
            
            # Settings
            '''
            0. CV_CAP_PROP_POS_MSEC Current position of the video file in milliseconds.
            1. CV_CAP_PROP_POS_FRAMES 0-based index of the frame to be decoded/captured next.
            2. CV_CAP_PROP_POS_AVI_RATIO Relative position of the video file
            3. CV_CAP_PROP_FRAME_WIDTH Width of the frames in the video stream.
            4. CV_CAP_PROP_FRAME_HEIGHT Height of the frames in the video stream.
            5. CV_CAP_PROP_FPS Frame rate.
            6. CV_CAP_PROP_FOURCC 4-character code of codec.
            7. CV_CAP_PROP_FRAME_COUNT Number of frames in the video file.
            8. CV_CAP_PROP_FORMAT Format of the Mat objects returned by retrieve() .
            9. CV_CAP_PROP_MODE Backend-specific value indicating the current capture mode.
            10. CV_CAP_PROP_BRIGHTNESS Brightness of the image (only for cameras).
            11. CV_CAP_PROP_CONTRAST Contrast of the image (only for cameras).
            12. CV_CAP_PROP_SATURATION Saturation of the image (only for cameras).
            13. CV_CAP_PROP_HUE Hue of the image (only for cameras).
            14. CV_CAP_PROP_GAIN Gain of the image (only for cameras).
            15. CV_CAP_PROP_EXPOSURE Exposure (only for cameras).
            16. CV_CAP_PROP_CONVERT_RGB Boolean flags indicating whether images should be converted to RGB.
            17. CV_CAP_PROP_WHITE_BALANCE Currently unsupported
            18. CV_CAP_PROP_RECTIFICATION Rectification flag for stereo cameras (note: only supported by DC1394 v 2.x backend currently)
            '''
            self.vid.set(cv2.CAP_PROP_FRAME_WIDTH,640)
            self.vid.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
            self.vid.set(cv2.CAP_PROP_FPS, 25)

            if not self.vid.isOpened():
                raise ValueError("Unable to open video source", self.video_source)

            #  Get video source width and height
            self.width = self.vid.get(cv2.CAP_PROP_FRAME_WIDTH)
            self.height = self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT)


        self.latest_frame = False, np.zeros([640, 480, 3])
        self.update_event = update_event

        self.stop = Event()
        self.start_thread()

    def update_cam(self):
        # run continuously and update the latest frame
        while not (self.stop.is_set() and self.update_event.is_set()):
            self.latest_frame = self.get_frame()
            self.update_event.set()

    def start_thread(self):
        self.update_thread = Thread(target=self.update_cam)
        self.update_thread.start()
    
    def stop_thread(self):
        self.stop.set()

    def get_frame(self):
        if self.video_source == "WiFi":
            """ LAN Camera: """
            rpi_name, image = self.image_hub.recv_image()
            self.image_hub.send_reply(b'OK')
            image = cv2.flip(image, 1)

            return True, image

        else:
            """ HW Camera:"""
            if self.vid.isOpened():
                ret, frame = self.vid.read()
                if ret:
                    #  Return a boolean success flag and the current frame converted to BGR
                    return (ret, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                else:
                    return (ret, None)
            else:
                return (ret, None)

    # Release the video source when the object is destroyed
    def __del__(self):
        self.stop_thread()
        if self.video_source != -1:
            if self.vid.isOpened():
                self.vid.release()

            

class Graph:
    def __init__(self, calibration, measure_height=312, width=640, height=480, data_intensity_range = 100, data_nm_min=200, data_nm_range=600, plot_nm_min=300, plot_nm_range=400):
        self.calibrate(calibration[0], calibration[1])


        self.measure_height = tkinter.IntVar(value=measure_height)
        self.sensor_width = 1000

        self.graph_width = width
        self.graph_height = height
        self.axis_offset = 40

        self.data_intensity_range = data_intensity_range
        self.data_nm_min = data_nm_min
        self.data_nm_range = data_nm_range

        self.plot_nm_min = plot_nm_min
        self.plot_nm_range = plot_nm_range
        self.plot_intensity_min = 0
        self.plot_intensity_range = 100

        self.plot_y_unit = "%"


        self.usemask = False
        self.mask = np.zeros(data_nm_range, dtype=float)

        self.flip = False


        # arrays for data
        self.exposure = 1
        self.exposure_progress = 0
        self.scans = [np.zeros(data_nm_range, dtype=float)]
        self.latest_data = np.zeros(data_nm_range, dtype=float)
        
        # settings
        self.draw_color = False

        self.draw_grid = True
        
        self.holdpeaks = False
        
        self.filter_level = 0 # savgol filter polynomial

        # peak detect
        self.label_peaks = False
        self.mindist = 50 # minumum distance between peaks
        self.thresh = 20 # Threshold


    def calibrate(self, wavelengths, pixels):
        # calculate the ranges
        delta_nm = abs(wavelengths[0]-wavelengths[1]) # how many nm between points 1 and 2?
        delta_px = abs(pixels[0]-pixels[1]) # how many px between pixels 1 and 2?

        # how many nm per pixel?
        self.calibrated_nmperpx = delta_nm/delta_px

        # reverse and wavelength of zeroth pixel
        if (wavelengths[1]-wavelengths[0]) * (pixels[1]-pixels[0]) >= 0:
            self.calibrated_reverse = False
            self.calibrated_nm_zero = wavelengths[0]-(pixels[0]/self.calibrated_nmperpx)
        else:
            self.calibrated_reverse = True
            self.calibrated_nm_zero = wavelengths[1]-(pixels[1]/self.calibrated_nmperpx)

        print(self.calibrated_nm_zero)
        print(self.calibrated_reverse)
        


    def update_data(self, latest_frame):
        ret, frame = latest_frame
        if ret:
            # greyscale the data (single dimension)
            bwimage = cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            rows, self.sensor_width = bwimage.shape

            # pull out single row of data
            pixel_row = np.zeros(self.sensor_width)
            for i in range(self.sensor_width):
                pixel_row[i] = bwimage[self.measure_height.get()-1 or 0, i]
                # TODO measure on an angle
            
            # convert to true wavelengths via calibration
            # reverse
            if self.calibrated_reverse:
                pixel_row = np.flip(pixel_row)
            # scale
            print("scaling from", len(pixel_row), "to", int(self.sensor_width / self.calibrated_nmperpx))

            wavelengths = cv2.resize(np.array([pixel_row]), (int(self.sensor_width / self.calibrated_nmperpx), 1), interpolation=cv2.INTER_AREA)[0]

            print(len(wavelengths))
            # slice
            print("slicing to", self.calibrated_nm_zero)
            if self.calibrated_nm_zero < self.data_nm_min:
                wavelengths = wavelengths[self.data_nm_min-round(self.calibrated_nm_zero):]
            if len(wavelengths) > self.data_nm_range:
                wavelengths = wavelengths[:self.data_nm_range]


            # save to data array (if smaller rest will be zero)
            scan = np.zeros([self.data_nm_range])
            np.put(scan, range(round(self.calibrated_nm_zero)-self.data_nm_min, len(scan)), wavelengths)

            # scale y
            scan = scan * self.data_intensity_range / 255
            scan = np.around(scan, 4)

            # average scans
            self.scans.append(scan)
            if len(self.scans) > self.exposure:
                self.scans = self.scans[len(self.scans)-self.exposure:]

            self.latest_data = np.average(self.scans, axis=0)

            # update progressbar
            self.exposure_progress += 1
            if self.exposure_progress > self.exposure:
                self.exposure_progress = 0
    

    def nm_to_rgb(self,nm):
        # from: https://www.codedrome.com/exploring-the-visible-spectrum-in-python/
        # returns RGB vals for a given wavelength
        gamma = 0.8
        max_intensity = self.data_intensity_range
        factor = 0

        rgb = {"R": 0, "G": 0, "B": 0}

        if 380 <= nm <= 439:
            rgb["R"] = -(nm - 440) / (440 - 380)
            rgb["G"] = 0.0
            rgb["B"] = 1.0
        elif 440 <= nm <= 489:
            rgb["R"] = 0.0
            rgb["G"] = (nm - 440) / (490 - 440)
            rgb["B"] = 1.0
        elif 490 <= nm <= 509:
            rgb["R"] = 0.0
            rgb["G"] = 1.0
            rgb["B"] = -(nm - 510) / (510 - 490)
        elif 510 <= nm <= 579:
            rgb["R"] = (nm - 510) / (580 - 510)
            rgb["G"] = 1.0
            rgb["B"] = 0.0
        elif 580 <= nm <= 644:
            rgb["R"] = 1.0
            rgb["G"] = -(nm - 645) / (645 - 580)
            rgb["B"] = 0.0
        elif 645 <= nm <= 780:
            rgb["R"] = 1.0
            rgb["G"] = 0.0
            rgb["B"] = 0.0

        if 380 <= nm <= 419:
            factor = 0.3 + 0.7 * (nm - 380) / (420 - 380)
        elif 420 <= nm <= 700:
            factor = 1.0
        elif 701 <= nm <= 780:
            factor = 0.3 + 0.7 * (780 - nm) / (780 - 700)

        if rgb["R"] > 0:
            rgb["R"] = int(max_intensity * ((rgb["R"] * factor) ** gamma))
        else:
            rgb["R"] = 0

        if rgb["G"] > 0:
            rgb["G"] = int(max_intensity * ((rgb["G"] * factor) ** gamma))
        else:
            rgb["G"] = 0

        if rgb["B"] > 0:
            rgb["B"] = int(max_intensity * ((rgb["B"] * factor) ** gamma))
        else:
            rgb["B"] = 0

        return (rgb["R"], rgb["G"], rgb["B"])
    
    def nm_to_plotx(self, nm):
        return int((nm-self.plot_nm_min) / self.plot_nm_range * (self.graph_width - self.axis_offset) + self.axis_offset)
    def plotx_to_nm(self, x):
        return ((x-self.axis_offset) / (self.graph_width - self.axis_offset) * self.plot_nm_range) + self.plot_nm_min
    def intensity_to_ploty(self, intensity):
        # TODO vertical zoom
        return int(self.graph_height - intensity / self.data_intensity_range * (self.graph_height - self.axis_offset) - self.axis_offset)
    def ploty_to_intensity(self, y):
        return (self.graph_height - (y + self.axis_offset)) * self.data_intensity_range / (self.graph_height - self.axis_offset)


    def get_graph_bg(self, y_label_interval=10, nm_label_interval=50):
        # Display a graticule calibrated with cal data
        
        # create a blank image
        graph = np.zeros([self.graph_height, self.graph_width,3],dtype=np.uint8)
        graph.fill(255) # fill white
        
        # graticule X
        font =cv2.FONT_HERSHEY_SIMPLEX
        
        for nm in range(self.plot_nm_min, self.plot_nm_min + self.plot_nm_range+1):
            if nm % (nm_label_interval // 5) == 0:
                x = self.nm_to_plotx(nm)
                # grey lines for subdivisions
                if self.draw_grid:
                    cv2.line(graph,(x,0), (x,self.graph_height-self.axis_offset+3), (200,200,200),1)

                if nm % nm_label_interval == 0:
                    cv2.line(graph,(x,0), (x,self.graph_height-self.axis_offset+3), (50,50,50),1)
                    cv2.putText(graph, str(nm) + 'nm', (x-8, self.graph_height-24),font,0.4,(0,0,0),1, cv2.LINE_AA)
        
        # graticulate Y
        for i in range (self.plot_intensity_min, self.plot_intensity_min+self.plot_intensity_range+1):
            if y_label_interval >= 5 and self.draw_grid:
                if i % (y_label_interval // 5) == 0:
                    y = self.intensity_to_ploty(i)
                    cv2.line(graph, (self.axis_offset, y), (self.graph_width, y), (200,200,200), 1)
                
            if i % y_label_interval == 0:
                y = self.intensity_to_ploty(i)

                cv2.line(graph, (self.axis_offset, y), (self.graph_width, y), (50,50,50), 1)
                cv2.putText(graph, str(i).rjust(4) + self.plot_y_unit, (0, y+12),font,0.4,(0,0,0),1, cv2.LINE_AA)

        return graph
    
    
    def label_peaks(self, graph):
        if self.label_peaks:
        # find peaks and label them
            thresh = int(self.thresh) # make sure the data is int.
            indexes = peakutils.indexes(self.latest_data, thres=thresh/max(self.latest_data), min_dist=self.mindist)
            textoffset = 12
            font = cv2.FONT_HERSHEY_SIMPLEX
            for i in indexes:
                height = self.latest_data[i]
                height = 480-height
                wavelength = int(self.calibrated_nm_zero+(i*self.calibrated_nmperpx))
                cv2.rectangle(graph,((i-textoffset)-2,height+3),((i-textoffset)+45,height-11),(255,255,0),-1)
                cv2.rectangle(graph,((i-textoffset)-2,height+3),((i-textoffset)+45,height-11),(0,0,0),1)
                cv2.putText(graph,str(wavelength)+'nm',(i-textoffset,height),font,0.4,(0,0,0),1, cv2.LINE_AA)

    def generate_graph(self, frame, update_event):
        if update_event.is_set():
            self.update_data(frame)
            update_event.clear()

            if self.usemask:
                for i in range(self.data_nm_range):
                    # avoid zeros
                    if 0 in (self.latest_data[i], self.mask[i]): continue

                    print(self.latest_data[i], self.mask[i], self.latest_data[i] / self.mask[i])
                    self.latest_data[i] = -log(self.latest_data[i] / self.mask[i]/3*100, 10)

            if self.filter_level > 0:
                self.latest_data = savgol_filter(self.latest_data,17,17-int(self.filter_level))

        if self.usemask:
            self.plot_intensity_range = 3
            self.data_intensity_range = 3
            self.plot_y_unit = "A"
            graph = self.get_graph_bg(y_label_interval=1)
        else:
            self.plot_intensity_range = 100
            self.data_intensity_range = 100
            self.plot_y_unit = "%"
            graph = self.get_graph_bg()

        graph = self.plot(graph, self.latest_data, (255, 0, 0))
        
        if self.usemask:
            graph = self.plot(graph, self.mask/100*3, (255, 255, 0))

        return graph

    def plot(self, graph, data, color=(255, 0, 0)):
        # create array of points
        plot = np.zeros([self.data_nm_range, 2], dtype=int)

        for nm in range(self.data_nm_range):
            # origin is top left.
            plot[nm][0] = self.nm_to_plotx(nm+self.data_nm_min)
            plot[nm][1] = self.intensity_to_ploty(data[nm])

        if self.draw_color:
            # for each index, plot a verital line derived from int
            # use waveleng_to_rgb to false color the data.
            #TODO increase brightness

            for i in range(len(plot)):
                wavelength = i + self.data_nm_min
                r,g,b =self.nm_to_rgb(wavelength)
                
                cv2.line(graph, (plot[i][0],self.graph_height-self.axis_offset), (plot[i][0],plot[i][1]), (r,g,b), 2)  # (start x,y) (end x,y) (color) thickness
        
        # plot the line
        #plot_arr = np.array(plot).reshape((-1,1,2)).astype(np.int32)        
        cv2.polylines(graph, np.int32([plot]), isClosed = False, color = color, thickness = 1, lineType = cv2.LINE_AA)

        return graph
        
    

#  Create a window and pass it to the Application object
app = App("OpenSpectrometerV2")
app.cam.stop_thread()

