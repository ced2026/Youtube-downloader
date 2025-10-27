import wx
import wx.grid
import yt_dlp
import threading
import requests
from io import BytesIO
from PIL import Image
import os
import re
from typing import Optional, List
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

class YouTubeDownloader(wx.Frame):
    def __init__(self):
        super().__init__(None, title="YouTube Downloader (yt_dlp)", size=(1100, 600))
        panel = wx.Panel(self)
        self.video_list, self.selected_rows = [], set()
        self.curr_path="D:\YouTube_download_path"
        self.input_url=""
        self.playlist_url=""
        self.isplaylist=False
        # Layout
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        # URL and Path Input
        self.url_text = wx.TextCtrl(panel)
        self.path_text = wx.TextCtrl(panel,value=self.curr_path)
        browse_btn = wx.Button(panel, label="Browse")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.url_text.Bind(wx.EVT_TEXT, self.on_fetch)
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        path_sizer.Add(self.path_text, 1)
        path_sizer.Add(browse_btn, 0, wx.LEFT, 5)

        left_sizer.Add(wx.StaticText(panel, label="YouTube URL:"), 0, wx.LEFT | wx.TOP, 10)
        left_sizer.Add(self.url_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        left_sizer.Add(wx.StaticText(panel, label="Download Path:"), 0, wx.LEFT | wx.TOP, 10)
        left_sizer.Add(path_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        # Format and Fetch
        format_sizer = wx.BoxSizer(wx.HORIZONTAL)
        #self.format_choice = wx.Choice(panel, choices=["Best Video+Audio", "Audio Only", "720p", "360p"])
        #self.format_choice.SetSelection(0)
        fetch_btn = wx.Button(panel, label="Fetch Videos")
        fetch_btn.Bind(wx.EVT_BUTTON, self.on_fetch)
        #format_sizer.Add(wx.StaticText(panel, label="Format:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        #format_sizer.Add(self.format_choice)
        format_sizer.Add(fetch_btn, 0, wx.LEFT, 10)
        left_sizer.Add(format_sizer, 0, wx.LEFT | wx.TOP, 10)

        # Grid
        self.grid = wx.grid.Grid(panel)
        self.grid.CreateGrid(0, 7)
        self.grid.SetRowLabelSize(20)
        for i, col in enumerate(["✔", "Title", "ID", "%", "Speed", "ETA", "Size"]):
            self.grid.SetColLabelValue(i, col)
        self.grid.Bind(wx.grid.EVT_GRID_CELL_LEFT_CLICK, self.on_grid_click)
        self.grid.Bind(wx.grid.EVT_GRID_SELECT_CELL, self.on_select_row)
        left_sizer.Add(self.grid, 1, wx.EXPAND | wx.ALL, 10)

        
        # Download and Status
        download_btn = wx.Button(panel, label="Download Selected")
        download_btn.Bind(wx.EVT_BUTTON, self.on_download_selected)
        self.status_text = wx.StaticText(panel, label="")
        left_sizer.Add(download_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
        left_sizer.Add(self.status_text, 0, wx.LEFT | wx.BOTTOM, 10)

        self.output_log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_RICH2 | wx.TE_READONLY, size=(1, 120))
        left_sizer.Add(wx.StaticText(panel, label="Command Output:"), 0, wx.LEFT | wx.TOP, 10)
        left_sizer.Add(self.output_log, 0, wx.EXPAND | wx.LEFT  | wx.BOTTOM, 10)
        
        # Thumbnail panel
        #self.thumbnail = wx.StaticBitmap(panel, size=(320, 180))
        main_sizer.Add(left_sizer, 1, wx.EXPAND)
        #main_sizer.Add(self.thumbnail, 0, wx.RIGHT | wx.TOP, 10)

        panel.SetSizer(main_sizer)
        self.Centre()
        self.Show()

    def seconds_to_time(seconds):
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02}:{minutes:02}:{secs:02}"


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

    def parse_multiple_urls(input_string: str) -> List[str]:
        """
        Parse multiple URLs from input string separated by commas, spaces, newlines, or mixed formats.
        Handles complex mixed separators like "url1, url2 url3\nurl4".

        Args:
            input_string (str): String containing one or more URLs

        Returns:
            List[str]: List of cleaned URLs
        """
        # Use regex to split by multiple separators: comma, space, newline, tab
        urls = re.split(r'[,\s\n\t]+', input_string.strip())
        urls = [url.strip() for url in urls if url.strip()]

        # Validate URLs (basic YouTube URL check)
        valid_urls = []
        invalid_count = 0
        for url in urls:
            if 'youtube.com' in url or 'youtu.be' in url:
                valid_urls.append(url)
            elif url:  # Only show warning for non-empty strings
                print(f"⚠️  Skipping invalid URL: {url}")
                invalid_count += 1

        if invalid_count > 0:
            print(
                f"💡 Found {len(valid_urls)} valid YouTube URLs, skipped {invalid_count} invalid entries")

        return valid_urls

    def download_single_video(self,url: str, output_path: str, thread_id: int = 0) -> dict:
        """
        Download a single YouTube video or playlist.
        Args:
            url (str): YouTube URL to download
            output_path (str): Directory to save the download
            thread_id (int): Thread identifier for logging
        Returns:
            dict: Result status with success/failure info
        """
        format_selector = (
            # Try best video+audio combination first
            'bestvideo[height<=1080]+bestaudio/best[height<=1080]/'
            # Fallback to best available quality
            'best'
        )
        
        # Configure yt-dlp options for MP4 only
        ydl_opts = {
            'format': format_selector,
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
        }
        #url="https://www.youtube.com/watch?v=R4v_7hh4Yys"
        print(url)
        # Set different output templates for playlists and single videos
        if self.is_playlist_url(url):
            ydl_opts['outtmpl'] = os.path.join(
                output_path, '%(playlist_title)s', '%(playlist_index)s-%(title)s.%(ext)s')
            print(
                f"🎵 [Thread {thread_id}] Detected playlist URL. Downloading entire playlist...")
        else:
            ydl_opts['outtmpl'] = os.path.join(output_path, '%(title)s.%(ext)s')
            print(
                f"🎥 [Thread {thread_id}] Detected single video URL. Downloading video...")
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Download content
                ydl.download([url])
                return {
                    'url': url,
                    'success': True,
                    'message': f"✅ [Thread {thread_id}] Download completed successfully!"
                }
        except Exception as e:
            return {
                'url': url,
                'success': False,
                'message': f"❌ [Thread {thread_id}] Error: {str(e)}"
            }

    def download_youtube_content(self, urls: List[str], output_path: Optional[str] = None,
                                list_formats: bool = False, max_workers: int = 3) -> None:
        """
        Download YouTube content (single videos or playlists) in MP4 format only.
        Supports multiple URLs for simultaneous downloading.

        Args:
            urls (List[str]): List of YouTube URLs to download
            output_path (str, optional): Directory to save the downloads. Defaults to './downloads'
            list_formats (bool): If True, only list available formats without downloading
            max_workers (int): Maximum number of concurrent downloads
        """
        # Set default output path if none provided
        if output_path is None:
            output_path = os.path.join(os.getcwd(), 'downloads')

        # If user wants to list formats, do that for the first URL and return
        if list_formats:
            wx.CallAfter(self.log_output, "Available formats for the first provided URL:")
            self.get_available_formats(urls[0])
            return

        # Create output directory if it doesn't exist
        os.makedirs(output_path, exist_ok=True)

        wx.CallAfter(self.log_output,f"\n🚀 Starting download of {len(urls)} URL(s) with {max_workers} concurrent workers...")
        wx.CallAfter(self.log_output,f"📁 Output directory: {output_path}")
        wx.CallAfter(self.log_output,"-" * 60)

        # Download videos concurrently
        print(urls)
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all download tasks
            future_to_url = {
                executor.submit(self.download_single_video, url, output_path, i+1): url
                for i, url in enumerate(urls)
            }

            # Collect results as they complete
            for future in as_completed(future_to_url):
                result = future.result()
                results.append(result)
                wx.CallAfter(self.log_output,result['message'])

        # Print summary
        wx.CallAfter(self.log_output,"\n" + "=" * 60)
        wx.CallAfter(self.log_output,"📊 DOWNLOAD SUMMARY")
        print("=" * 60)

        successful = [r for r in results if r['success']]
        failed = [r for r in results if not r['success']]

        wx.CallAfter(self.log_output,f"✅ Successful downloads: {len(successful)}")
        wx.CallAfter(self.log_output,f"❌ Failed downloads: {len(failed)}")

        if failed:
            wx.CallAfter(self.log_output,"\n❌ Failed URLs:")
            for result in failed:
                wx.CallAfter(self.log_output,f"   • {result['url']}")
                wx.CallAfter(self.log_output,f"     Reason: {result['message']}")

        if successful:
            wx.CallAfter(self.log_output,f"\n🎉 All files saved to: {output_path}")

    
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

    def log_output(self, message):
        #self.output_log.AppendText(message + "\n")
        if isinstance(message, str):
            self.output_log.AppendText("Message:\n" + message + "\n")
        elif isinstance(message, list):
            self.output_log.AppendText("List:\n")
            for item in message:
                self.output_log.AppendText(f"- {item}\n")
        elif isinstance(message, dict):
            self.output_log.AppendText("Dictionary:\n")
            for key, value in message.items():
                self.output_log.AppendText(f"{key}: {value}\n")
        else:
            self.output_log.AppendText("Other:\n" + str(message) + "\n")



    def on_browse(self, _):
        dlg = wx.DirDialog(self, "Choose folder")
        if dlg.ShowModal() == wx.ID_OK:
            self.curr_path=dlg.GetPath()
            self.path_text.SetValue(self.curr_path)#(dlg.GetPath())
            
        dlg.Destroy()

    def on_fetch(self, _):
        
        self.input_url=self.url_text.GetValue().strip()
        #url =self.input_url
        #print(url)
        #print(self.is_playlist_url(url))
        if not self.input_url:
            self.status_text.SetLabel("Please enter a URL.")
            return
        self.status_text.SetLabel("Fetching...")
        threading.Thread(target=self.fetch_videos, args=(self.input_url,self.curr_path)).start()

    def fetch_videos(self, url,full_path):
        try:
            self.video_list.clear()
            with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                info = ydl.extract_info(url, download=False)
            self.title=info.get('title')
            if "list" in url:
                self.playlist_url=info.get('url')
                self.isplaylist=True
                with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
                    info = ydl.extract_info(self.playlist_url, download=False)
                    wx.CallAfter(self.log_output,self.log_output(info))
                    playlist_title=info['title']
                    self.curr_path = os.path.join(full_path,info['title'])#, '%(playlist_index)s-%(title)s.%(ext)s'
                    self.path_text.SetValue(self.curr_path)
                    #wx.CallAfter(self.log_output,self.log_output(f"🎵 [Thread {0}] Detected playlist URL. Downloading entire playlist..."))
        
            self.video_list = info['entries'] if 'entries' in info else [info]
            #print(self.video_list)
            #wx.CallAfter(self.log_output,f"   • {self.video_list}")

            wx.CallAfter(self.update_grid)
            wx.CallAfter(self.status_text.SetLabel, f"{len(self.video_list)} video(s) found.")
        except Exception as e:
            wx.CallAfter(self.status_text.SetLabel, f"Error: {str(e)}")

    def update_grid(self):
        self.grid.ClearGrid()
        if self.grid.GetNumberRows() > 0:
            self.grid.DeleteRows(0, self.grid.GetNumberRows())
        self.selected_rows.clear()
        for i, video in enumerate(self.video_list):
            self.grid.AppendRows(1)
            self.grid.SetCellValue(i, 0, "☐")
            self.grid.SetCellValue(i, 1, video.get("title", ""))
            self.grid.SetCellValue(i, 2, video.get("id", ""))
            self.grid.SetCellValue(i, 3, "___________________________")
            self.grid.SetCellValue(i, 4, "___________________________")
            self.grid.SetCellValue(i, 5, "_________________")
            self.grid.SetCellValue(i, 6, "_________________")
        self.grid.AutoSizeColumns()

    def on_grid_click(self, event):
        row, col = event.GetRow(), event.GetCol()
        if col == 0:
            mark = self.grid.GetCellValue(row, 0)
            self.grid.SetCellValue(row, 0, "☑" if mark == "☐" else "☐")
            (self.selected_rows.add if mark == "☐" else self.selected_rows.discard)(row)
        event.Skip()

    def on_select_row(self, event):
        row = event.GetRow()
        try:
            video = self.video_list[row]
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
                        
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 3, d.get('_percent_str', '').strip('% '))
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 4, d.get('_speed_str', '').strip())
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 5, str(d.get('eta', '')))
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 6, d.get('_total_bytes_str', '') or '')
                    elif d['status'] == 'finished':
                        wx.CallAfter(self.grid.SetCellValue, selected_row, 3, '100')
                    
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
                wx.CallAfter(self.log_output,self.log_output(url))
                wx.CallAfter(self.log_output,self.log_output(f"✅ [Thread {thread_id}] Download completed successfully!"))
                return {
                    'url': url,
                    'success': True,
                    'message': f"✅ [Thread {thread_id}] Download completed successfully!"
                }
        except Exception as e:
            wx.CallAfter(self.log_output,self.log_output(f"Error: {str(e)}"))
            return {
                'url': url,
                'success': False,
                'message': f"❌ [Thread {thread_id}] Error: {str(e)}"
            }

if __name__ == '__main__':
    app = wx.App(False)
    YouTubeDownloader()
    app.MainLoop()
