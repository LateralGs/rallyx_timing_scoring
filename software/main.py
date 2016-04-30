import logging
logging.basicConfig(level=logging.DEBUG)

import sys
import serial
import time
import sqlite3
import ConfigParser
import os
import csv

import Tkinter as tk
import ttk
import tkMessageBox as tkmb
import tkFileDialog as tkfd
import tkFont as tkf
import tkSimpleDialog
import ScrolledText as tkst

import tag_heuer_520
import rfid
import score_html_gen

################################################################################
################################################################################

car_class = {'SA':"Stock All",'PA':"Prepared All",'MA':"Modified All",
             'SF':"Stock Front",'PF':"Prepared Front",'MF':"Modified Front",
             'SR':"Stock Rear",'PR':"Prepared Rear",'MR':"Modified Rear",'TO':"Time Only"}


################################################################################
################################################################################

class TimingFrame(tk.Frame):
  def __init__(self, parent, event_db, config):
    tk.Frame.__init__(self, parent)
    self.pack()
    self.log = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    self.event_db = event_db
    self.config = config
    self.ui = {}
    self.var = {}

    self.create_ui()
    self.event_db.add_callback(self.event_db_callback)

  def create_ui(self):
    self.columns = ["start","finish","time","number","cones","gates","run"]
    self.headings = ["Start", "Finish", "Time", "#", "C", "G", "R"]

    self.var['next_driver_entry'] = tk.StringVar()
    self.var['next_driver_label'] = tk.StringVar()
    self.var['start_label'] = tk.StringVar()
    self.var['finish_label'] = tk.StringVar()
    self.var['cone'] = tk.IntVar()
    self.var['gate'] = tk.IntVar()
    self.var['driver'] = tk.StringVar()
    self.var['run_info'] = tk.StringVar()

    self.var['run_info'].set("Run #")
    self.var['start_label'].set("Start Ready")
    self.var['finish_label'].set("Finish Ready")
    self.var['next_driver_label'].set("000")

    self.ui['treeview_frame'] = tk.Frame(self)
    self.ui['treeview'] = ttk.Treeview(self.ui['treeview_frame'], selectmode='browse', columns=self.columns, takefocus=0)
    self.ui['hscroll'] = tk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.ui['treeview'].xview, takefocus=0)
    self.ui['vscroll'] = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.ui['treeview'].yview, takefocus=0)
    self.ui['treeview'].configure(yscrollcommand=self.ui['vscroll'].set, xscrollcommand=self.ui['hscroll'].set)

    self.ui['treeview'].grid(row=0, column=0, sticky='nsew', in_=self.ui['treeview_frame'])
    self.ui['hscroll'].grid(row=1, column=0, sticky='ew', in_=self.ui['treeview_frame'])
    self.ui['vscroll'].grid(row=0, column=1, sticky='ns', in_=self.ui['treeview_frame'])
    self.ui['treeview_frame'].grid_columnconfigure(0, weight=1)
    self.ui['treeview_frame'].grid_rowconfigure(0, weight=1)

    self.ui['treeview'].bind("<<TreeviewSelect>>", self.treeview_select_callback)

    for col in range(len(self.headings)):
      self.ui['treeview'].heading(col, text=self.headings[col])

    self.ui['treeview'].column("start", width=tkf.Font().measure(" 999.999 "))
    self.ui['treeview'].column("finish", width=tkf.Font().measure(" 999.999 "))
    self.ui['treeview'].column("time", width=tkf.Font().measure(" 999.999 "))
    self.ui['treeview'].column("number", width=tkf.Font().measure(" 9999 "))
    self.ui['treeview'].column("cones", width=tkf.Font().measure(" 99 "))
    self.ui['treeview'].column("gates", width=tkf.Font().measure(" 99 "))
    self.ui['treeview'].column("run", width=tkf.Font().measure(" 99 "))


    self.ui['treeview'].heading('#0')
    self.ui['treeview'].column('#0', width=10)

    self.ui['start_label'] = tk.Label(self, textvariable=self.var['start_label'], relief=tk.SUNKEN)
    self.ui['finish_label'] = tk.Label(self, textvariable=self.var['finish_label'], relief=tk.SUNKEN)

    self.ui['next_driver_label_frame'] = tk.LabelFrame(self, text="Next Driver")
    self.ui['run_label_frame'] = tk.LabelFrame(self, text="Run")

    self.ui['button_frame'] = tk.Frame(self)
    self.ui['false_finish_button'] = tk.Button(self.ui['button_frame'], text="False Finish", command=self.false_finish_button, takefocus=0)
    self.ui['false_start_button'] = tk.Button(self.ui['button_frame'], text="False Start", command=self.false_start_button, takefocus=0)
    self.ui['dnf_button'] = tk.Button(self.ui['button_frame'], text="DNF", command=self.dnf_button, takefocus=0)
    
    self.ui['next_driver_entry'] = tk.Entry(self.ui['next_driver_label_frame'], width=8, textvariable=self.var['next_driver_entry'])
    self.ui['next_driver_label'] = tk.Label(self.ui['next_driver_label_frame'], textvariable=self.var['next_driver_label'], relief=tk.RIDGE, width=8, justify=tk.CENTER)

    self.ui['driver_entry'] = tk.Entry(self.ui['run_label_frame'], textvariable=self.var['driver'])
    self.ui['cone_entry'] = tk.Entry(self.ui['run_label_frame'], textvariable=self.var['cone'])
    self.ui['gate_entry'] = tk.Entry(self.ui['run_label_frame'], textvariable=self.var['gate'])
    self.ui['cone_label'] = tk.Label(self.ui['run_label_frame'], text="Cones:")
    self.ui['gate_label'] = tk.Label(self.ui['run_label_frame'], text="Gates:")
    self.ui['driver_label'] = tk.Label(self.ui['run_label_frame'], text="Driver #:")
    self.ui['run_info_label'] = tk.Label(self.ui['run_label_frame'], textvariable=self.var['run_info'])
    self.ui['score_run_button'] = tk.Button(self.ui['run_label_frame'], text="Score Run", command=self.score_run_button)

    self.ui['start_label'].grid(row=0, column=0, sticky='ewns')
    self.ui['finish_label'].grid(row=0, column=1, sticky='ewns')
    self.ui['treeview_frame'].grid(row=1, column=0, columnspan=2)
    self.ui['next_driver_label_frame'].grid(row=0, column=2, sticky='ew')
    self.ui['run_label_frame'].grid(row=1, column=2, sticky='ns')

    self.ui['button_frame'].grid(row=2, column=0, columnspan=2, sticky='ew')
    self.ui['false_start_button'].grid(row=0, column=0, sticky='ew', padx=4)
    self.ui['false_finish_button'].grid(row=0, column=1, sticky='ew', padx=4)
    self.ui['dnf_button'].grid(row=0, column=2, sticky='ew', padx=4)

    self.ui['next_driver_label'].grid(row=0, column=0, sticky='e', padx=4, pady=4)
    self.ui['next_driver_entry'].grid(row=0, column=1, sticky='e')
    
    self.ui['driver_label'].grid(row=0, column=0, sticky='e')
    self.ui['driver_entry'].grid(row=0, column=1, sticky='w')
    self.ui['cone_label'].grid(row=1, column=0, sticky='e')
    self.ui['cone_entry'].grid(row=1, column=1, sticky='w')
    self.ui['gate_label'].grid(row=2, column=0, sticky='e')
    self.ui['gate_entry'].grid(row=2, column=1, sticky='w')
    self.ui['score_run_button'].grid(row=3, column=1, sticky='ew')
    self.ui['run_info_label'].grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=8)

    self.ui['driver_entry'].bind('<Key-Return>', self.focus_next)
    self.ui['cone_entry'].bind('<Key-Return>', self.focus_next)
    self.ui['gate_entry'].bind('<Key-Return>', self.focus_next)

    self.ui['next_driver_entry'].bind('<Key-Return>', self.next_driver_return_key)

  def next_driver_return_key(self, event):
    number = self.var['next_driver_entry'].get()
    if number.strip() != '':
      self.var['next_driver_label'].set(number)
      self.var['next_driver_entry'].set('')

  def focus_next(self, event):
    if event.widget == self.ui['driver_entry']:
      self.ui['cone_entry'].focus()
      self.ui['cone_entry'].select_range(0, tk.END)
    elif event.widget == self.ui['cone_entry']:
      self.ui['gate_entry'].focus()
      self.ui['gate_entry'].select_range(0, tk.END)
    elif event.widget == self.ui['gate_entry']:
      self.ui['driver_entry'].focus()
      self.ui['driver_entry'].select_range(0, tk.END)
  
  def false_start_button(self):
    pass # remove last start

  def false_finish_button(self):
    pass # remove last finish

  def dnf_button(self):
    pass

  def score_run_button(self):
    pass

  def treeview_select_callback(self, event):
    iid = self.ui['treeview'].focus()
    if iid == '' or iid in car_class:
      return
    # TODO
  
  def event_db_callback(self, action):
    if action == 'open':
      pass
    elif action == 'close':
      pass

################################################################################
################################################################################

class ScoringFrame(tk.Frame):
  def __init__(self, parent, event_db, config):
    tk.Frame.__init__(self, parent)
    self.pack()
    self.log = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    self.event_db = event_db
    self.config = config
    self.ui = {}
    self.var = {}
    self.create_ui()
    self.event_db.add_callback(self.event_db_callback)

  def create_ui(self):
    pass
  
  def event_db_callback(self, action):
    if action == 'open':
      pass
    elif action == 'close':
      pass

################################################################################
################################################################################

class DriversFrame(tk.Frame):
  def __init__(self, parent, event_db, config):
    tk.Frame.__init__(self, parent)
    self.pack()
    self.log = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    self.event_db = event_db
    self.config = config
    self.ui = {}
    self.var = {}
    self.create_ui()
    self.event_db.add_callback(self.event_db_callback)

  def create_ui(self):
    self.columns = ('first_name','last_name','number','tech','car_number','car_year','car_make','car_model','rfid')
    self.headings = ('First','Last','Driver #','Tech','Car #','Year','Make','Model','RFID #')

    self.ui['treeview_frame'] = tk.Frame(self)
    self.ui['treeview'] = ttk.Treeview(self.ui['treeview_frame'], selectmode='browse', columns=self.columns)
    self.ui['hscroll'] = tk.Scrollbar(self, orient=tk.HORIZONTAL, command=self.ui['treeview'].xview)
    self.ui['vscroll'] = tk.Scrollbar(self, orient=tk.VERTICAL, command=self.ui['treeview'].yview)
    self.ui['treeview'].configure(yscrollcommand=self.ui['vscroll'].set, xscrollcommand=self.ui['hscroll'].set)


    self.ui['treeview'].grid(row=0, column=0, sticky='nsew', in_=self.ui['treeview_frame'])
    self.ui['hscroll'].grid(row=1, column=0, sticky='ew', in_=self.ui['treeview_frame'])
    self.ui['vscroll'].grid(row=0, column=1, sticky='ns', in_=self.ui['treeview_frame'])
    self.ui['treeview_frame'].grid_columnconfigure(0, weight=1)
    self.ui['treeview_frame'].grid_rowconfigure(0, weight=1)
    self.ui['treeview_frame'].pack(fill=tk.BOTH, expand=1)

    self.ui['treeview'].bind("<<TreeviewSelect>>", self.treeview_select_callback)

    for col in range(len(self.headings)):
      self.ui['treeview'].heading(col, text=self.headings[col])
      if col < len(self.headings)-1:
        self.ui['treeview'].column(col, width=tkf.Font().measure(self.headings[col]))
        self.log.debug(tkf.Font().measure(self.headings[col]))

    self.ui['treeview'].heading('#0', text="Class")

    for cc in sorted(car_class.keys()):
      self.ui['treeview'].insert('', 'end', cc, text=car_class[cc])

    self.ui['add_button'] = tk.Button(self, text="Add Driver", command=self.add_driver)
    self.ui['remove_button'] = tk.Button(self, text="Remove Driver", command=self.remove_driver)
    self.ui['edit_button'] = tk.Button(self, text="Edit Driver", command=self.edit_driver)

  def add_driver(self):
    pass

  def remove_driver(self):
    iid = self.ui['treeview'].focus()
    if iid == '' or iid in car_class:
      return

    first_name = self.ui['treeview'].set(iid,'first_name')
    last_name = self.ui['treeview'].set(iid,'last_name')

    if tkmb.askyesno("Remove Driver", "Are you sure you want to remove the driver?\n"+first_name + ' ' + last_name, parent=self):
      self.event_db.db.execute("DELETE FROM driver WHERE rowid=?", (iid,))
      self.update_drivers()

  def edit_driver(self):
    iid = self.ui['treeview'].focus()
    if iid == '' or iid in car_class:
      return



  def treeview_select_callback(self, event):
    iid = self.ui['treeview'].focus()
    if iid == '' or iid in car_class:
      return
    # TODO

  def update_drivers(self):
    # delete everything and rebuild
    for cc in sorted(car_class.keys()):
      self.ui['treeview'].delete(cc)
      self.ui['treeview'].insert('', 'end', cc, text=car_class[cc], open=True)

    for row in self.event_db.db.execute("SELECT rowid,* FROM driver"):
      if row['class'] in car_class:
        self.ui['treeview'].insert(row['class'], 'end', row['rowid'], text=row['class'])
        for col in self.columns:
          self.ui['treeview'].set(row['rowid'], col, row[col])
      else:
        self.log.error("Driver class is not correct")
  
  def event_db_callback(self, action):
    if action == 'open':
      self.update_drivers()
    elif action == 'close':
      pass
    elif action == 'import':
      self.update_drivers()

################################################################################
################################################################################

class EditDriverDialog(tkSimpleDialog.Dialog):
  def __init__(self, parent, title, event_db, config, driver_id=None):
    self.log = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    self.event_db = event_db
    self.config = config
    self.driver_id = None
    self.ui = {}
    self.var = {}
    tkSimpleDialog.Dialog.__init__(self, parent, title=title)

  def body(self, parent):
    pass

  def validate(self):
    return True

  def apply(self):
    pass


################################################################################
################################################################################

class EventFrame(tk.Frame):
  def __init__(self, parent, event_db, config):
    tk.Frame.__init__(self, parent)
    self.pack()
    self.log = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    self.event_db = event_db
    self.config = config
    self.ui = {}
    self.var = {}
    self.create_ui()
    self.event_db.add_callback(self.event_db_callback)

  def create_ui(self):
    self.var['organization'] = tk.StringVar()
    self.var['location'] = tk.StringVar()
    self.var['season_points'] = tk.IntVar()
    self.var['other_info'] = tk.StringVar()
    self.var['date'] = tk.StringVar()

    self.ui['general_label_frame'] = tk.LabelFrame(self, text="General Info")
    self.ui['organization_label'] = tk.Label(self.ui['general_label_frame'], text="Organization:")
    self.ui['organization_entry'] = tk.Entry(self.ui['general_label_frame'], textvariable=self.var['organization'], width=40)
    self.ui['location_label'] = tk.Label(self.ui['general_label_frame'], text="Location:")
    self.ui['location_entry'] = tk.Entry(self.ui['general_label_frame'], textvariable=self.var['location'], width=40)
    self.ui['date_label'] = tk.Label(self.ui['general_label_frame'], text="Date:")
    self.ui['date_entry'] = tk.Entry(self.ui['general_label_frame'], textvariable=self.var['date'], width=40)
    self.ui['season_points_label'] = tk.Label(self.ui['general_label_frame'], text="Season Points:")
    self.ui['season_points_check'] = tk.Checkbutton(self.ui['general_label_frame'], variable=self.var['season_points'])
    
    self.ui['organization_label'].grid(column=0, row=0, sticky=tk.E)
    self.ui['organization_entry'].grid(column=1, row=0)
    self.ui['location_label'].grid(column=0, row=1, sticky=tk.E)
    self.ui['location_entry'].grid(column=1, row=1)
    self.ui['date_label'].grid(column=0, row=2, sticky=tk.E)
    self.ui['date_entry'].grid(column=1, row=2)
    self.ui['season_points_label'].grid(column=0, row=3, sticky=tk.E)
    self.ui['season_points_check'].grid(column=1, row=3, sticky=tk.W)

    self.ui['other_label_frame'] = tk.LabelFrame(self, text="Other Info")
    self.ui['other_info_text'] = tkst.ScrolledText(self.ui['other_label_frame'], height=10)
    self.ui['other_info_text'].grid(row=0,column=0,sticky='nsew')

    self.ui['save_button'] = tk.Button(self, text="Save Changes", command=self.save_button)

    self.ui['save_button'].grid(row=0, column=1, pady=4, sticky='ns')
    self.ui['general_label_frame'].grid(row=0, column=0, sticky='ew')
    self.ui['other_label_frame'].grid(row=1, column=0, columnspan=2, sticky='nsew')

  def save_button(self):
    self.event_db.registry_set('organization', self.var['organization'].get())
    self.event_db.registry_set('location', self.var['location'].get())
    self.event_db.registry_set('date', self.var['date'].get())
    self.event_db.registry_set('season_points', self.var['season_points'].get())
    self.event_db.registry_set('other_info', self.ui['other_info_text'].get('1.0', tk.END))

  def event_db_callback(self, action):
    if action == 'open':
      self.var['organization'].set(self.event_db.registry_get('organization',''))
      self.var['location'].set(self.event_db.registry_get('location',''))
      self.var['date'].set(self.event_db.registry_get('date',''))
      self.var['season_points'].set(self.event_db.registry_get('season_points',1))
      self.ui['other_info_text'].delete('1.0', tk.END)
      self.ui['other_info_text'].insert('1.0', self.event_db.registry_get('other_info',''))
    elif action == 'close':
      self.save_button()


################################################################################
################################################################################

class EventDatabase(object):
  def __init__(self, root=None, event_path=None):
    self.log = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    self.db = None
    self.root = root
    self.callbacks = []
    self.open(event_path)

  def add_callback(self, func):
    if not callable(func):
      self.log.error("invalid callback func, %r", func)
    elif func not in self.callbacks:
      self.callbacks.append(func)

  def remove_callback(self, func):
    if func in self.callbacks:
      self.callbacks.remove(func)

  def broadcast_callback(self, action):
    for func in self.callbacks:
      func(action)

  def is_open(self):
    return self.db is not None

  def close(self):
    if self.db:
      self.log.debug("close")
      self.broadcast_callback("close") # call before closing giving things an oportunity commit changes
      self.db.close()
      self.db = None

  def open(self, event_path, create_new=False):
    if event_path is None or event_path == "":
      return
    self.close()
    self.log.debug("event_path = %r", event_path)

    if create_new and os.path.exists(event_path):
      # backup file instead of deleting
      count = 0
      while os.path.exists(event_path + ".old." + str(count)):
        count += 1
      os.rename(event_path, event_path + ".old." + str(count))

    try:
      self.db = sqlite3.connect(event_path)
      self.db.row_factory = sqlite3.Row
    except sqlite3.Error as e:
      self.db = None
      self.log.error(e)
      tkmb.showerror("Error", "Unable to open event database", parent=self.root)
      return
    self.create_tables()
    self.broadcast_callback("open")

  def create_tables(self):
    self.db.execute("CREATE TABLE IF NOT EXISTS registry(key PRIMARY KEY, value)")
    self.db.execute("CREATE TABLE IF NOT EXISTS driver(class, first_name, last_name, number UNIQUE, rfid UNIQUE, tech, car_year, car_make, car_model, car_number, UNIQUE(first_name, last_name))")
    self.db.execute("CREATE TABLE IF NOT EXISTS run(start, finish, time, number, cones, gates, dnf)")
    self.db.commit()

  def registry_get(self, key, default=None):
    value = self.db.execute("SELECT value FROM registry WHERE key=?", (key,)).fetchone()
    if value is None:
      self.log.debug(default)
      return default
    else:
      self.log.debug(value[0])
      return value[0]

  def registry_set(self, key, value):
    self.db.execute("INSERT OR REPLACE INTO registry (key,value) values (?,?)", (key,value))
    self.db.commit()


################################################################################
################################################################################

class Application(object):
  def __init__(self, root=tk.Tk(), event_path=None, config_path=None):
    self.log = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    self.root = root

    self.event_db = EventDatabase(root, event_path)

    # load config file
    if config_path is None:
      config_path = os.path.dirname(os.path.realpath(__file__)) + "/config.ini"

    self.config = ConfigParser.RawConfigParser()
    self.config.read(config_path)

    self.create_ui()

  def mainloop(self):
    self.root.mainloop()

  def create_ui(self):
    self.root.title("ORG RallyX Timing & Scoring")

    # main menu
    self.menubar = tk.Menu(self.root)
    self.file_menu = tk.Menu(self.menubar, tearoff=0)
    self.file_menu.add_command(label="Open Event", command=self.file_menu_open_event)
    self.file_menu.add_command(label="New Event", command=self.file_menu_new_event)
    self.file_menu.add_separator()
    self.file_menu.add_command(label="Import Drivers", command=self.file_menu_import_drivers)
    self.file_menu.add_separator()
    self.file_menu.add_command(label="Exit", command=self.file_menu_exit)
    self.menubar.add_cascade(label="File", menu=self.file_menu)
    self.root.config(menu=self.menubar)

    # window close handler
    self.root.protocol("WM_DELETE_WINDOW", self.file_menu_exit)

    self.no_event_label = tk.Label(self.root, justify=tk.CENTER, text="No event open.")
    self.no_event_label.pack(fill=tk.X)

    self.notebook = ttk.Notebook(self.root, takefocus=False)
    self.event_frame = EventFrame(self.notebook, self.event_db, self.config)
    self.timing_frame = TimingFrame(self.notebook, self.event_db, self.config)
    self.scoring_frame = ScoringFrame(self.notebook, self.event_db, self.config)
    self.drivers_frame = DriversFrame(self.notebook, self.event_db, self.config)
    self.notebook.add(self.event_frame,   text="  Event  ")
    self.notebook.add(self.timing_frame,  text="  Timing  ")
    self.notebook.add(self.scoring_frame, text="  Scoring  ")
    self.notebook.add(self.drivers_frame, text="  Drivers  ")
    # pack this later when we have an open event
    #self.notebook.pack(fill=tk.BOTH, expand=1, pady=(8,0))


  def file_menu_import_drivers(self):
    if not self.event_db.is_open():
      tkmb.showwarning("Import Warning", "You must open or create a new event prior to importing driver data.", parent=self.root)
      return
    csv_file = tkfd.askopenfile(parent=self.root, title="Import Driver CSV", defaultextension=".csv", filetypes=[("CSV File","*.csv")])
    if csv_file is None:
      return
    csv_reader = csv.DictReader(csv_file)
    for row in csv_reader:
      self.log.debug(row)
      row['class'] = row['class'].upper()
      if row['class'] not in car_class.keys():
        self.log.error("invalid car class, %r", row['class'])
      else:
        if 'rfid' in row and row['rfid'].strip() == '':
          row['rfid'] = None
        if 'number' in row and row['number'].strip() == '':
          row['number'] = None
        try:
          self.event_db.db.execute("INSERT INTO driver(class, first_name, last_name, number, rfid, tech, car_year, car_make, car_model, car_number) values (:class,:first_name,:last_name,:number,:rfid,:tech,:car_year,:car_make,:car_model,:car_number)", row)
        except sqlite3.Error as e:
          self.log.error(e)
    self.event_db.db.commit()
    csv_file.close()
    self.event_db.broadcast_callback("import")
    

  def file_menu_open_event(self):
    self.event_db.open(tkfd.askopenfilename(parent=self.root, title="Open Event", defaultextension=".db", filetypes=[("Event Database","*.db")]))
    if self.event_db.db is not None:
      self.no_event_label.pack_forget()
      self.notebook.pack(fill=tk.BOTH, expand=1, pady=(8,0))

  def file_menu_new_event(self):
    self.event_db.open(tkfd.asksaveasfilename(parent=self.root, title="New Event", defaultextension=".db", filetypes=[("Event Database","*.db")]), create_new=True)
    if self.event_db.db is not None:
      self.no_event_label.pack_forget()
      self.notebook.pack(fill=tk.BOTH, expand=1, pady=(8,0))

  def file_menu_exit(self):
    if tkmb.askokcancel("Exit","Do you really want to exit?"):
      self.event_db.close()
      self.root.destroy()


################################################################################
################################################################################

if __name__ == "__main__":
  app = Application()
  app.mainloop()

