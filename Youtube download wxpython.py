import wx
import wx.grid
import wx.grid as gridlib
import yt_dlp
import threading
import os
from urllib.parse import urlparse, parse_qs
import subprocess


class MediaEntry:
    def __init__(self, url: str, title: str, file_path: str, is_playlist: bool):
        self.url = url
        self.title = title
        self.file_path = file_path
        self.is_playlist = is_playlist

    def __repr__(self):
        return (f"MediaEntry(title='{self.title}', url='{self.url}', "
                f"path='{self.file_path}', playlist={self.is_playlist})")
    def __str__(self):
        return f"{self.title}|{self.url}|{self.file_path}|{int(self.is_playlist)}"
    def to_csv_line(self):
        # Escape commas if needed
        return f"{self.title},{self.url},{self.file_path},{int(self.is_playlist)}"
    @staticmethod
    def from_csv_line(line: str):
        parts = line.strip().split(",")
        if len(parts) == 4:
            title, url, file_path, is_playlist = parts
            return MediaEntry(url, title, file_path, bool(int(is_playlist)))
        return None
    @staticmethod
    def from_string(line: str):
        parts = line.strip().split("|")
        if len(parts) == 4:
            title, url, file_path, is_playlist = parts
            return MediaEntry(url, title, file_path, bool(int(is_playlist)))
        return None

class MediaLibrary:
    def __init__(self):
        self.entries = []

    def add_entry(self, url: str, title: str, file_path: str, is_playlist: bool):
        if url in [e.url for e in self.entries]:
            wx.MessageBox("This URL already exists in the library.", "Duplicate Entry", wx.OK | wx.ICON_WARNING)    
            return  # Avoid duplicates
        else:
            entry = MediaEntry(url, title, file_path, is_playlist)
            self.entries.append(entry)

    def get_all(self):
        return self.entries
    
    def get_by_indx(index):
        return self.entries[index]
    
    def find_by_title(self, keyword: str):
        return [e for e in self.entries if keyword.lower() in e.title.lower()]
    
    def find_by_url(self, keyword: str):
        return [e for e in self.entries if keyword.lower() in e.url.lower()]

    def find_playlists(self):
        return [e for e in self.entries if e.is_playlist]

    def __repr__(self):
        return f"MediaLibrary({len(self.entries)} entries)"
    def save_to_csv(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("Title,URL,FilePath,IsPlaylist\n")
            for entry in self.entries:
                f.write(entry.to_csv_line() + "\n")

    def load_from_csv(self, path):
        self.entries.clear()
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[1:]:  # Skip header
                entry = MediaEntry.from_csv_line(line)
                if entry:
                    self.entries.append(entry)

# Example usage
#library = MediaLibrary()
#library.add_entry("https://example.com/video1", "Intro to Python", "/videos/python_intro.mp4", False)
#library.add_entry("https://example.com/playlist1", "Python Tutorials", "/videos/python_playlist.m3u", True)

    
class YouTubeDownloader(wx.Frame):
    def __init__(self):
        super().__init__(None, title="YouTube Downloader (yt_dlp)", size=(1100, 900))#style = wx.DEFAULT_FRAME_STYLE|wx.MAXIMIZE|wx.TAB_TRAVERSAL )
        
        self.video_list, self.selected_rows = [], set()
        #self.Urls = (set())
        self.storage = MediaLibrary()
        self.curr_entity=MediaEntry("", "", "", False)
        self.curr_path="D:\YouTube_download_path"
        self.input_url=""
        self.playlist_url=""
        self.isplaylist=False
        

        # create menu
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_OPEN, "&Open\tCtrl+O", "Open .ydl file")
        file_menu.Append(wx.ID_SAVE, "&Save\tCtrl+S", "Save to .ydl file")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT, "E&xit\tCtrl+Q", "Exit the application")
        menubar.Append(file_menu, "&File")

        self.SetMenuBar(menubar)
        self.Bind(wx.EVT_MENU, self.OnOpen, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.OnSave, id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self.OnExit, id=wx.ID_EXIT)

        # Layout
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)
        # URL and Path Input
        self.url_text = wx.TextCtrl(panel)
        fetch_btn = wx.Button(panel, label="Fetch Videos")
        fetch_btn.Bind(wx.EVT_BUTTON, self.on_fetch)
        self.path_text = wx.TextCtrl(panel,value=self.curr_path)
        browse_btn = wx.Button(panel, label="Browse")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.url_text.Bind(wx.EVT_TEXT,self.modify_url_txt)# self.url_text_modify)
        self.path_text.Bind(wx.EVT_TEXT, self.on_path_modify)
        Url_sizer = wx.BoxSizer(wx.HORIZONTAL)
        Url_sizer.Add(self.url_text, 1)
        Url_sizer.Add(fetch_btn, 0, wx.LEFT, 5)
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        path_sizer.Add(self.path_text, 1)
        path_sizer.Add(browse_btn, 0, wx.LEFT, 5)

        left_sizer.Add(wx.StaticText(panel, label="YouTube URL:"), 0, wx.LEFT | wx.TOP, 10)
        left_sizer.Add(Url_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        left_sizer.Add(wx.StaticText(panel, label="Download Path:"), 0, wx.LEFT | wx.TOP, 10)
        left_sizer.Add(path_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Format and Fetch
        format_sizer = wx.BoxSizer(wx.HORIZONTAL)
        #self.format_choice = wx.Choice(panel, choices=["Best Video+Audio", "Audio Only", "720p", "360p"])
        #self.format_choice.SetSelection(0)
        #fetch_btn = wx.Button(panel, label="Fetch Videos")
        #fetch_btn.Bind(wx.EVT_BUTTON, self.on_fetch)
        #format_sizer.Add(wx.StaticText(panel, label="Format:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        #format_sizer.Add(self.format_choice)
        #format_sizer.Add(fetch_btn, 0, wx.LEFT, 10)
        #left_sizer.Add(format_sizer, 0, wx.LEFT | wx.TOP, 10)

        self.radio1 = wx.RadioButton(panel, label="Display Title", style=wx.RB_GROUP)
        self.radio2 = wx.RadioButton(panel, label="Display URL")
        self.radio1.Bind(wx.EVT_RADIOBUTTON, self.on_radio)
        self.radio2.Bind(wx.EVT_RADIOBUTTON, self.on_radio)

        hbox_radio = wx.BoxSizer(wx.HORIZONTAL)
        hbox_radio.Add(self.radio1, 0, wx.ALL, 5)
        hbox_radio.Add(self.radio2, 0, wx.ALL, 5)

        # add list box
        grid_list_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.list_box = wx.ListBox(panel, style=wx.LB_SINGLE| wx.LB_HSCROLL ) #choices=["Item 1", "Item 2", "Item 3", "Item 4"]
        self.list_box.SetMinSize((600, 400))
        self.list_box.SetMaxSize((500, 1000))

        self.list_box.Bind(wx.EVT_LISTBOX,self.select_listbox_item)
        
        # delete and clear the data
        self.delete_btn = wx.Button(panel, label="Delete item")
        self.delete_btn.Bind(wx.EVT_BUTTON, self.delete_data)
        self.Clear_btn = wx.Button(panel, label="Clear all")
        self.Clear_btn.Bind(wx.EVT_BUTTON, self.clear_data)
        self.delete_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.delete_sizer.Add(self.delete_btn, 0, wx.EXPAND | wx.ALL, 5)
        self.delete_sizer.Add(self.Clear_btn, 0, wx.EXPAND | wx.ALL, 5)
        #status text
        self.status_text = wx.StaticText(panel, label="")
        font = wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.status_text.SetFont(font) # Set font
        self.status_text.SetForegroundColour(wx.Colour(255, 0, 0)) # Set text color to red

        
        hbox_radio_listbox = wx.BoxSizer(wx.VERTICAL)
        hbox_radio_listbox.Add(hbox_radio, 0, wx.ALL, 5)
        hbox_radio_listbox.Add(self.list_box, 0, wx.EXPAND | wx.ALL, 5)
        hbox_radio_listbox.Add(self.delete_sizer, 0, wx.EXPAND | wx.ALL, 5)
        hbox_radio_listbox.Add(self.status_text, 0, wx.EXPAND | wx.ALL, 5)
        grid_list_sizer.Add(hbox_radio_listbox, 1, wx.EXPAND | wx.ALL, 10)
        
        # left side
        self.Title_Lb = wx.StaticText(panel, label="Title: ")
        font = wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.Title_Lb.SetFont(font) # Set font
        self.Title_Lb.SetForegroundColour(wx.Colour(0, 0, 255)) # Set text color to red
        # Grid
        self.grid = wx.grid.Grid(panel)
        self.grid.CreateGrid(0, 6)
        self.grid.SetRowLabelSize(20)
        for i, col in enumerate(["✔", "Title", "ID", "%", "Speed", "Left time"]):#, "Size"
            self.grid.SetColLabelValue(i, col)
        self.grid.SetMinSize((900, 500))
        self.grid.SetMaxSize((900, 900))
        # Checkbox column setup
        self.bool_attr = gridlib.GridCellAttr()
        self.bool_attr.SetEditor(gridlib.GridCellBoolEditor())
        self.bool_attr.SetRenderer(gridlib.GridCellBoolRenderer())
        self.green_attr = gridlib.GridCellAttr()
        self.green_attr.SetBackgroundColour(wx.Colour(144, 238, 144))  # light green
        
        
        self.grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.on_grid_click)
        #self.grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.on_select_row)
        # Download and Status
        download_btn = wx.Button(panel, label="Download Selected")
        download_btn.Bind(wx.EVT_BUTTON, self.on_download_selected)
        self.check_box = wx.CheckBox(panel, label="Select all")
        self.check_box.Bind(wx.EVT_CHECKBOX , self.on_select_all)
        hbox_chechbox_dowenload = wx.BoxSizer(wx.HORIZONTAL)
        hbox_chechbox_dowenload.Add(download_btn, 0, wx.ALL, 5)
        hbox_chechbox_dowenload.Add(self.check_box, 0, wx.ALL, 5)
        
        vbox_grid = wx.BoxSizer(wx.VERTICAL)
        vbox_grid.Add(self.Title_Lb, 0, wx.ALL, 5)
        vbox_grid.Add(self.grid, 0, wx.ALL, 5)
        vbox_grid.Add(hbox_chechbox_dowenload, 0, wx.ALL, 5)
        
        grid_list_sizer.Add(vbox_grid, 2, wx.EXPAND | wx.ALL, 10)
        
        left_sizer.Add(grid_list_sizer, 0, wx.EXPAND | wx.ALL, 10)

        
        #left_sizer.Add(self.check_box, 0, wx.ALIGN_LEFT | wx.BOTTOM, 10)
        #left_sizer.Add(download_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        #left_sizer.Add(self.status_text, 0, wx.LEFT | wx.BOTTOM, 10)

        self.output_log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_READONLY, size=(1, 120))
        left_sizer.Add(wx.StaticText(panel, label="Command Output:"), 0, wx.LEFT | wx.TOP, 10)
        left_sizer.Add(self.output_log, 0, wx.EXPAND | wx.LEFT  | wx.BOTTOM, 10)
        
        # Thumbnail panel
        #self.thumbnail = wx.StaticBitmap(panel, size=(320, 180))
        main_sizer.Add(left_sizer, 1, wx.EXPAND)
        #main_sizer.Add(self.thumbnail, 0, wx.RIGHT | wx.TOP, 10)

        panel.SetSizer(main_sizer)
        self.Maximize(True)
        self.Centre()
        self.Show()

    def seconds_to_time(self,seconds):
        if seconds is None:
            return "00:00:00"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs =round(seconds % 60, 2) 
        return f"{hours:02}:{minutes:02}:{secs:02}"

    def getchars(self,s,c='%',num_chars=5):
        index = s.find(c)
        tt=""
        if index >= num_chars:
            tt= s[index-num_chars:index]
        return tt  # Not enough characters before %

    def log_output(self, message):
        #self.output_log.AppendText(message + "\n")
        if isinstance(message, str):
            self.output_log.AppendText("Output:\n" + message + "\n")
        elif isinstance(message, list|set|tuple):
            self.output_log.AppendText("List:\n")
            for item in message:
                self.output_log.AppendText(f"- {item}\n")
        
        elif isinstance(message, dict):
            self.output_log.AppendText("Dictionary:\n")
            for key, value in message.items():
                self.output_log.AppendText(f"{key}: {value}\n")
        else:
            self.output_log.AppendText("Other:\n" + str("None") + "\n")
        self.output_log.AppendText("===============================================================================\n")

    def RefreshDisplay(self):
        self.list_box.Clear()
        for entry in self.library.get_all():
            self.self.list_box.Append(f"{entry[0]}\n")

    def is_playlist_url(self,url: str) -> bool:
        """
        Check if the provided URL is a playlist or a single video.

        Args:
            url (str): YouTube URL to check

        Returns:
            bool: True if URL is a playlist, False if single video
        """
        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)
        #print(query_params)
        return 'list' in query_params

    def fill_list(self, _):
        self.list_box.Clear()
        #self.grid.ClearGrid()
        for entry in self.storage.entries:
            self.list_box.Append(entry.title)
        if self.list_box.GetCount()>0:
            self.list_box.SetSelection(0)
        self.curr_entity=self.storage.entries[0]    
        #self.input_url=curr_entity.url
        #selection
        #self.list_box.SetSelection(self.list_box.GetCount()-1)
        evt = wx.CommandEvent(wx.EVT_LISTBOX.typeId, self.list_box.GetId())
        evt.SetEventObject(self.list_box)
        wx.PostEvent(self.list_box, evt)


    
    
    """ not used functions"""
    def get_available_formats(self,url: str) -> None: 
        """
        List available formats for debugging purposes.

        Args:
            url (str): YouTube URL to check formats for
        """
        ydl_opts = {
            'listformats': True,
            'quiet': False
        }

    def merge_audio_video(video_file, audio_file, output_file):
        command = [
            'ffmpeg',
            '-i', video_file,
            '-i', audio_file,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-strict', 'experimental',
            '-y',  # overwrite output
            output_file
        ]

        subprocess.run(command)
        print(f"Merged into: {output_file}")

#events
    def OnOpen(self, event):
        with wx.FileDialog(self, "Open .ydl file", wildcard="*.ydl",style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                try:
                    self.storage.load_from_csv(path)
                    self.fill_list(self)
                    #self.RefreshDisplay()
                except Exception as e:
                    wx.MessageBox(f"Failed to open file:\n{e}", "Error", wx.OK | wx.ICON_ERROR)

    def OnSave(self, event):
        with wx.FileDialog(self, "Save .ydl file", wildcard="*.ydl",style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                path = dlg.GetPath()
                try:
                    self.storage.save_to_csv(path)
                    wx.MessageBox("Library saved successfully.", "Saved", wx.OK | wx.ICON_INFORMATION)
                except Exception as e:
                    wx.MessageBox(f"Failed to save file:\n{e}", "Error", wx.OK | wx.ICON_ERROR)

    def OnExit(self, event):
        self.Close(True)
    
    def clear_data(self,_):
        self.storage.entries.clear()
        self.list_box.Clear()
        self.grid.ClearGrid()
        self.status_text.SetLabel("Cleared all data.")
        self.Title_Lb.SetLabel("Cleared all data.")
    def delete_data(self,_):
        selected_index = self.list_box.GetSelection()
        if selected_index != wx.NOT_FOUND:
            del self.storage.entries[selected_index]
            self.list_box.Delete(selected_index)
            self.grid.ClearGrid()
            self.status_text.SetLabel("Deleted selected item.")  
            self.list_box.SetSelection(0)  
    def modify_url_txt(self,event):
        input_url=self.url_text.GetValue().strip()
        self.rest_path()
        if self.storage.find_by_url(input_url) :#if url in [e.url for e in self.storage.entries]:
            self.status_text.SetLabel( "This URL already exists in the library, and has been feched.")
            self.log_output("URL already fetched:" +self.curr_entity.url)
            wx.MessageBox("This URL already exists in the library.", "Duplicate Entry", wx.OK | wx.ICON_WARNING)
            #make select on list box
            event.Skip()
        else:
            self.curr_entity.url=input_url#self.url_text.GetValue().strip()
            self.rest_path()
            self.on_fetch(self)
        
    def on_browse(self, _):
        dlg = wx.DirDialog(self, "Choose folder")
        if dlg.ShowModal() == wx.ID_OK:
            self.curr_path=dlg.GetPath()
            self.path_text.SetValue(self.curr_path)#(dlg.GetPath())
        dlg.Destroy()

    def on_path_modify(self, _):
        #self.curr_path=self.path_text.GetValue().strip()
        return

    def rest_path(self):
        self.curr_path="D:\YouTube_download_path"
        self.path_text.SetValue(self.curr_path)    

    def on_radio(self, event):
        #selected =event.GetEventObject().GetValue()#.Getindex()  #
        selected =event.GetEventObject().GetLabel()
        
        if selected=="Display Title":
            self.list_box.Clear()
            for entry in self.storage.entries:
                self.list_box.Append(entry.title)
        else: #"Display URL":
            self.list_box.Clear()
            for entry in self.storage.entries:
                self.list_box.Append(entry.url)
    
        # selected_index = self.list_box.GetSelection()
        # if selected_index != wx.NOT_FOUND:
        #     selected_value = self.list_box.GetString(selected_index)
        #     if self.radio1.GetValue():  # Display Title
        #         self.url_text.SetValue(selected_value)
        #     elif self.radio2.GetValue():  # Display URL
        #         self.url_text.SetValue(selected_value)
        event.Skip()

    def select_listbox_item(self, event):
        selected_index = self.list_box.GetSelection()
        self.curr_entity=self.storage.entries[selected_index]
        #self.input_url=self.curr_entity.url
        self.rest_path()
        self.on_fetch(self)
        # if selected_index != wx.NOT_FOUND:
        #     self.input_url = self.list_box.GetString(selected_index)
        #     self.url_text.SetValue(self.input_url)
        event.Skip()

    def on_fetch(self, event):
        if 'youtube.com' in self.curr_entity.url or 'youtu.be' in self.curr_entity.url:
            self.log_output("Found valid URL:" +self.curr_entity.url+"\n Please wiat untill found all files.")
            #self.Urls.add(self.input_url)
            self.status_text.SetLabel("Fetching...............................")
            threading.Thread(target=self.fetch_videos, args=(self.curr_entity.url,self.curr_path)).start()
        elif self.curr_entity.url:  # Only show warning for non-empty strings
            self.output_log.AppendText(f"⚠️  Skipping invalid URL: {self.curr_entity.url}\n Please enter a URL.")
            self.status_text.SetLabel("Please enter correct URL.")
    
        if not self.curr_entity.url:
            self.status_text.SetLabel("Please enter correct URL.")
            return

    def fetch_videos(self, url,full_path):
        try:
            self.video_list.clear()
            #if is_playlist_url(url):
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(url, download=False)
            self.title=info.get('title')
            self.video_list = info['entries'] if 'entries' in info else [info]
            self.isplaylist=False
            if "list" in url:
                self.playlist_url=info.get('url')
                #self.playlist_videos_count=info.get('playlist_count')
                self.isplaylist=True
                with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    info = ydl.extract_info(self.playlist_url, download=False)
                    #wx.CallAfter(self.log_output,self.log_output(info))
                    #self.title=info['title']
                self.curr_path = os.path.join(full_path,info['title'])#, '%(playlist_index)s-%(title)s.%(ext)s'
                self.path_text.SetValue(self.curr_path)
                    #wx.CallAfter(self.log_output,self.log_output(f"🎵 [Thread {0}] Detected playlist URL. Downloading entire playlist..."))
        
                self.video_list = info['entries'] if 'entries' in info else [info]
                self.log_output("number of fetched videos:" +str(len(self.video_list)))#self.video_list))
                wx.CallAfter(self.status_text.SetLabel, f"{len(self.video_list)} video(s) found.")
                
            self.curr_entity = MediaEntry(url, self.title, self.curr_path, self.isplaylist)
            if url in [e.url for e in self.storage.entries]:
                wx.CallAfter(self.status_text.SetLabel, "This URL has been feched.")
                # Avoid duplicates
            else:
                self.storage.add_entry(url, self.title, self.curr_path, self.isplaylist)
                self.list_box.Append(self.curr_entity.title)#if url in [e.url for e in self.entries] len(self.storage)-1
            #self.list_box.SetSelection(self.list_box.GetCount()-1)
            wx.CallAfter(self.update_grid)
        except Exception as e:
            wx.CallAfter(self.status_text.SetLabel, f"Error: {str(e)}")

    def update_grid(self):
        self.grid.ClearGrid()
        for row in range(self.grid.GetNumberRows() - 1, -1, -1) :#in range(self.grid.GetNumberRows()):
            for col in range(self.grid.GetNumberCols()):
                self.grid.SetCellEditor(row, col, None)
                self.grid.SetCellRenderer(row, col, None)
            self.grid.DeleteRows(pos=row, numRows=1)

        label="Title: " + self.curr_entity.title
        self.Title_Lb.SetLabel(label)
        #if self.curr_entity.is_playlist:
        # self.grid.AppendRows(1)
        # self.grid.SetCellSize(0, 0, 1,self.grid.GetNumberCols())
        # self.grid.SetCellValue(0, 0, self.curr_entity.title or "Playlist Title")
        # self.grid.SetBackgroundColour(wx.Colour(144, 238, 144))
        # self.grid.SetCellAlignment(0, 0, wx.ALIGN_CENTRE, wx.ALIGN_CENTRE)
            
        #if self.grid.GetNumberRows() > 0:
        #    self.grid.DeleteRows(0, self.grid.GetNumberRows())
        self.selected_rows.clear()
        for i, video in enumerate(self.video_list):
            self.grid.AppendRows(1)
            #self.grid.SetCellValue(i, 0, "☐")
            #self.grid.SetCellValue(i+nrows, 0,str(i+1))
            self.grid.SetAttr(i, 0, self.bool_attr.Clone())
            self.grid.SetCellValue(i, 0, '0')  # unchecked
            self.grid.SetCellValue(i, 1, video.get("title", ""))
            self.grid.SetCellValue(i, 2, video.get("id", ""))
            #self.grid.SetAttr(i, 3, self.progress_attr.Clone())
            self.grid.SetCellValue(i, 3, "__________")
            self.grid.SetCellValue(i, 4, "__________")
            self.grid.SetCellValue(i, 5, "______________")
            #self.grid.SetCellValue(i, 6, "_________________")
        #to avoid to select the first row
        self.grid.AutoSizeColumns()
        self.grid.SetAttr(0, 0, self.bool_attr.Clone())
        self.grid.SetCellValue(0, 0, '1' )
        self.selected_rows.add(0)

    def on_grid_click(self, event):
        row, col = event.GetRow(), event.GetCol()
        if col == 0:
            # if row==0:
            #     self.check_box.SetValue(True)
            #     self.on_select_all(self,event)
            
            mark = self.grid.GetCellValue(row, 0)
            self.grid.SetAttr(row, 0, self.bool_attr.Clone())
            self.grid.SetCellValue(row, 0, '1' if mark == '0' else '0')
            mark = self.grid.GetCellValue(row, 0)
            if mark=='1':
                self.selected_rows.add(row)
            else:
                self.selected_rows.discard(row)
            #self.grid.SetCellValue(row, 0, "☑" if mark == "☐" else "☐")
            #(self.selected_rows.add if mark == "☐" else self.selected_rows.discard)(row)
            #print(self.selected_rows)
            self.log_output(f"Selected rows: {self.selected_rows}")
        event.Skip()
    
    def on_select_all(self, event):
        try:
            checked = self.check_box.GetValue()
            value = '1' if checked else '0'
            for row in range(self.grid.GetNumberRows()):
                self.grid.SetCellValue(row, 0, value)
                #(self.selected_rows.add if self.grid.GetCellValue(row,0) == 0 else self.selected_rows.discard)(row)
                if checked:
                    self.selected_rows.add(row)
                else:
                    self.selected_rows.discard(row)
            self.log_output(f"Selected rows: {self.selected_rows}")        
        except Exception:
            pass
        event.Skip()
        
    def on_select_row(self, event):
        row = event.GetRow()
        try:
            self.log_output("Selected row: "+ row)
            #video = self.video_list[row]
            #thumb_url = video.get('thumbnail') or f"https://img.youtube.com/vi/{video['id']}/0.jpg"
            #img_data = requests.get(thumb_url).content
            #img = wx.Image(BytesIO(img_data)).Scale(320, 180)
            #self.thumbnail.SetBitmap(wx.Bitmap(img))
        except Exception:
            pass
        event.Skip()
    

    def on_download_selected(self, _):
        path = self.curr_path #.path_text.GetValue().strip()
        if not path or not self.selected_rows:
            self.status_text.SetLabel("Select path and videos first.")
            return
        #curr_url = f"https://www.youtube.com/watch?v={ self.grid.GetCellValue(0, 2)}"
        #wx.CallAfter(self.log_output,curr_url)
        selected = [(i, self.video_list[i]) for i in self.selected_rows]
        #print (selected) #wx.CallAfter(self.log_output,f"{for i in selected}")
        #fmt = self.format_choice.GetStringSelection()
        #threading.Thread(target=self.download_videos, args=(selected, path, fmt)).start()
        #for i in self.selected_rows:
        for row, video in selected:
            print(video)
            url = f"https://www.youtube.com/watch?v={video['id']}"
            threading.Thread(target=self.download_single_video1, args=(url, path,0,row)).start()
        #self.download_youtube_content([curr_url],path)
        #xx=["https://www.youtube.com/watch?v=a2srHUwtob8&list=PLcQHTE-X8-qjoEAFnzqw9XVsIP4g_nbLJ&index=3"]
        #threading.Thread(target=self.download_youtube_content, args=(xx, path)).start()
    def download_single_video1(self,url: str, output_path: str, thread_id: int = 0,selected_row:int=0) -> dict:
        """
        Download a single YouTube video or playlist.
        Args:
            url (str): YouTube URL to download
            output_path (str): Directory to save the download
            thread_id (int): Thread identifier for logging
        Returns:
            dict: Result status with success/failure info
        """
        def hook(d):
                    if d['status'] == 'downloading':
                        p=d.get('_percent_str', '').strip('% ')
                        s=d.get('_speed_str', '').strip()
                        eta=d.get('eta', '')
                        tt=self.getchars( p,'%',5)
                        sp=self.getchars( s,'K',7)+'kb'
                        eta_hms=self.seconds_to_time(eta)
                        #wx.CallAfter(self.grid.SetAttr(selected_row, 3, self.progress_attr.Clone()))
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 3,tt+'%')
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 4,sp )
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 5,str(eta_hms) )
                        #wx.CallAfter(self.grid.SetCellValue, selected_row, 5, d.get('_total_bytes_str', '') or '')
                        
                        #wx.CallAfter(self.log_output,self.log_output(p))
                        xt=self.getchars(p,'%',5)
                        wx.CallAfter(self.log_output,"Precent ="+xt+"%, Speed ="+sp+", Left time ="+eta_hms)
                    elif d['status'] == 'finished':
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 3, '100%')
                        wx.CallAfter(self.grid.SetCellBackgroundColour, selected_row, 3, wx.Colour(144, 238, 144))
                        url = f"https://www.youtube.com/watch?v={self.grid.GetCellValue(selected_row, 2)}"
                        wx.CallAfter(self.log_output,"✅file no." + str(selected_row+1)+" "+url+" downloaded")
                        
                    
        format_selector = (
            # Try best video+audio combination first
            'bestvideo[height<=1080]+bestaudio/best[height<=1080]/'
            # Fallback to best available quality
            'best'
        )
        
        # Configure yt-dlp options for MP4 only
        ydl_opts = {
            #'format': format_selector,
            'merge_output_format': 'mp4',
            'ignoreerrors': True,
            'no_warnings': False,
            'extract_flat': False,
            # Disable all additional downloads for clean MP4-only output
            'writesubtitles': False,
            'writethumbnail': False,
            'writeautomaticsub': False,
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            # Clean up options
            'keepvideo': False,
            'clean_infojson': True,
            'retries': 3,
            'fragment_retries': 3,
            'progress_hooks': [hook],
        }
        # Set different output templates for playlists and single videos
        if self.isplaylist:
            ydl_opts['outtmpl'] = os.path.join(output_path, '%(playlist_index)s-%(title)s.%(ext)s')#'%(playlist_title)s'
            print( f"🎵 [Thread {thread_id}] Detected playlist URL. Downloading entire playlist...")
        else:
            ydl_opts['outtmpl'] = os.path.join(output_path, '%(title)s.%(ext)s')
            print( f"🎥 [Thread {thread_id}] Detected single video URL. Downloading video...")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download content
                ydl.download([url])
                #wx.CallAfter(self.log_output,self.log_output(url))
                #wx.CallAfter(self.log_output,"✅ [Thread "+thread_id+"] Download completed successfully!")
                return {
                    'url': url,
                    'success': True,
                    'message': f"✅ [Thread {thread_id}] Download completed successfully!"
                }
        except Exception as e:
            wx.CallAfter(self.log_output,"Error: {"+str(e)+"}")
            return {
                'url': url,
                'success': False,
                'message': f"❌ [Thread {thread_id}] Error: {str(e)}"
            }
            

if __name__ == '__main__':
    app = wx.App(False)
    YouTubeDownloader()
    app.MainLoop()


