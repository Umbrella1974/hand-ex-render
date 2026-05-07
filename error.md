D:\Anaconda2020\Anaconda\envs\hand-ex-render\lib\site-packages\pygame\pkgdata.py:25: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.
  from pkg_resources import resource_stream, resource_exists
pygame 2.6.1 (SDL 2.28.4, Python 3.9.25)
Hello from the pygame community. https://www.pygame.org/contribute.html
Traceback (most recent call last):
  File "D:\11111code\hand-ex-render\hand_viewer_pygame.py", line 275, in <module>
    main()
  File "D:\11111code\hand-ex-render\hand_viewer_pygame.py", line 270, in main
    viewer = HandViewer(args)
  File "D:\11111code\hand-ex-render\hand_viewer_pygame.py", line 79, in __init__
    self.font = pygame.font.SysFont("consolas", 14)
  File "D:\Anaconda2020\Anaconda\envs\hand-ex-render\lib\site-packages\pygame\sysfont.py", line 416, in SysFont
    initsysfonts()
  File "D:\Anaconda2020\Anaconda\envs\hand-ex-render\lib\site-packages\pygame\sysfont.py", line 355, in initsysfonts
    fonts = initsysfonts_win32()
  File "D:\Anaconda2020\Anaconda\envs\hand-ex-render\lib\site-packages\pygame\sysfont.py", line 82, in initsysfonts_win32
    if splitext(font)[1].lower() not in OpenType_extensions:
  File "D:\Anaconda2020\Anaconda\envs\hand-ex-render\lib\ntpath.py", line 205, in splitext
    p = os.fspath(p)
TypeError: expected str, bytes or os.PathLike object, not int