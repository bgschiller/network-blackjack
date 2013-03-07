from Tkinter import *
from ScrolledText import *

class App(object):
    def __init__(self,master):
        topframe = Frame(master)
        topframe.pack()
        self.views = Frame(topframe)
        self.views.pack()
        self.controls = Frame(topframe)
        self.controls.pack()

        self.button = Button(self.controls, text='Quit', fg='red',
                command=topframe.quit)
        self.button.pack(side=RIGHT)
        self.hi_there = Button(self.controls, text='Hello',
                command=self.say_hi)
        self.hi_there.pack(side=RIGHT)

        self.textwindow = ScrolledText(self.views, width=90)
        self.textwindow.pack(side=TOP)
        self.chatline = Entry(self.controls)
        self.chatline.pack(side=BOTTOM)

    def say_hi(self):
        print 'Hi there, everyone!'


root = Tk()
root.title('Chatting with Python')
app = App(root)

root.mainloop()



