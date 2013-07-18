import os
import subprocess
import ssh
import wx
import wx.lib.newevent
import re
from StringIO import StringIO
import logging
from threading import *
import threading
import time
import sys
from os.path import expanduser
import subprocess
import traceback
import socket
from utilityFunctions import logger_debug, logger_error, HelpDialog
import pkgutil

OPENSSH_BUILD_DIR = 'openssh-cygwin-stdin-build'

if not sys.platform.startswith('win'):
    import pexpect

def is_pageant_running():
    username = os.path.split(os.path.expanduser('~'))[-1]
    return 'PAGEANT.EXE' in os.popen('tasklist /FI "USERNAME eq %s"' % username).read()

def start_pageant():
    if is_pageant_running():
        # Pageant pops up a dialog box if we try to run a second
        # instance, so leave immediately.
        return

    if hasattr(sys, 'frozen'):
        pageant = os.path.join(os.path.dirname(sys.executable), OPENSSH_BUILD_DIR, 'bin', 'PAGEANT.EXE')
    else:
        #pageant = os.path.join(os.getcwd(), OPENSSH_BUILD_DIR, 'bin', 'PAGEANT.EXE')
        launcherModulePath = os.path.dirname(pkgutil.get_loader("launcher").filename)
        pageant = os.path.join(launcherModulePath, OPENSSH_BUILD_DIR, 'bin', 'PAGEANT.EXE')

    import win32process
    subprocess.Popen([pageant], creationflags=win32process.DETACHED_PROCESS)

def double_quote(x):
    return '"' + x + '"'

class sshpaths():
    def ssh_binaries(self):
        """
        Locate the ssh binaries on various systems. On Windows we bundle a
        stripped-down OpenSSH build that uses Cygwin.
        """

        useDirtyHack = False
        if sys.platform.startswith('win'):
            if useDirtyHack:
                # Dirty hack: a non-administrator user on Windows XP can't run charade.exe
                # because it tries to create a temporary file in the Cygwin OpenSSH tree. So
                # we'll quietly copy it to the user's home directory and run it from there instead.

                if hasattr(sys, 'frozen'):
                    ssh_base_directory = os.path.join(os.path.dirname(sys.executable), OPENSSH_BUILD_DIR)
                else:
                    launcherModulePath = os.path.dirname(pkgutil.get_loader("launcher").filename)
                    ssh_base_directory = os.path.join(launcherModulePath, OPENSSH_BUILD_DIR)

                import tempfile
                import distutils.dir_util

                for d in os.listdir(os.path.expanduser('~')):
                    if d.find('.' + OPENSSH_BUILD_DIR) != 0: continue

                    full_path = os.path.join(os.path.expanduser('~'), d)
                    try:
                        logger_debug('Attempting to remove openssh temp directory: ' + str(d))
                        distutils.dir_util.remove_tree(full_path)
                    except:
                        logger_debug('Could not remove temp directory, exception: ' + str(traceback.format_exc()))
                        pass

                user_ssh_directory = tempfile.mkdtemp(prefix='.' + OPENSSH_BUILD_DIR, dir=os.path.expanduser('~'))

                logger_debug('copying system OpenSSH binaries from <%s> to <%s>' % (ssh_base_directory, user_ssh_directory,))
                distutils.dir_util.copy_tree(ssh_base_directory, user_ssh_directory)

                f = lambda x: os.path.join(user_ssh_directory, 'bin', x)
            else:
                # Don't use dirty hack.
                # Assume that our InnoSetup script will set appropriate permissions on the "tmp" directory.

                 if hasattr(sys, 'frozen'):
                    f = lambda x: os.path.join(os.path.dirname(sys.executable), OPENSSH_BUILD_DIR, 'bin', x)
                 else:
                    launcherModulePath = os.path.dirname(pkgutil.get_loader("launcher").filename)
                    f = lambda x: os.path.join(launcherModulePath, OPENSSH_BUILD_DIR, 'bin', x)

            sshBinary        = double_quote(f('ssh.exe'))
            sshKeyGenBinary  = double_quote(f('ssh-keygen.exe'))
            sshKeyScanBinary = double_quote(f('ssh-keyscan.exe'))
            sshAgentBinary   = double_quote(f('charade.exe'))
            sshAddBinary     = double_quote(f('ssh-add.exe'))
            chownBinary      = double_quote(f('chown.exe'))
            chmodBinary      = double_quote(f('chmod.exe'))
        elif sys.platform.startswith('darwin'):
            sshBinary        = '/usr/bin/ssh'
            sshKeyGenBinary  = '/usr/bin/ssh-keygen'
            sshKeyScanBinary = '/usr/bin/ssh-keyscan'
            sshAgentBinary   = '/usr/bin/ssh-agent'
            sshAddBinary     = '/usr/bin/ssh-add'
            chownBinary      = '/usr/sbin/chown'
            chmodBinary      = '/bin/chmod'
        else:
            sshBinary        = '/usr/bin/ssh'
            sshKeyGenBinary  = '/usr/bin/ssh-keygen'
            sshKeyScanBinary = '/usr/bin/ssh-keyscan'
            sshAgentBinary   = '/usr/bin/ssh-agent'
            sshAddBinary     = '/usr/bin/ssh-add'
            chownBinary      = '/bin/chown'
            chmodBinary      = '/bin/chmod'
 
        return (sshBinary, sshKeyGenBinary, sshAgentBinary, sshAddBinary, sshKeyScanBinary, chownBinary, chmodBinary,)
    
    def ssh_files(self):
        known_hosts_file = os.path.join(expanduser('~'), '.ssh', 'known_hosts')
        sshKeyPath = os.path.join(expanduser('~'), '.ssh', self.keyFileName)
        if self.massiveLauncherConfig is not None:
            self.massiveLauncherConfig.set("MASSIVE Launcher Preferences", "massive_launcher_private_key_path", sshKeyPath)
            with open(self.massiveLauncherPreferencesFilePath, 'wb') as massiveLauncherPreferencesFileObject:
                self.massiveLauncherConfig.write(massiveLauncherPreferencesFileObject)

        return (sshKeyPath,known_hosts_file,)

    def __init__(self, keyFileName, massiveLauncherConfig=None, massiveLauncherPreferencesFilePath=None):
        (sshBinary, sshKeyGenBinary, sshAgentBinary, sshAddBinary, sshKeyScanBinary,chownBinary, chmodBinary,) = self.ssh_binaries()
        self.keyFileName                = keyFileName
        self.massiveLauncherConfig      = massiveLauncherConfig
        self.massiveLauncherPreferencesFilePath = massiveLauncherPreferencesFilePath
        (sshKeyPath,sshKnownHosts,)     = self.ssh_files()
        self.sshBinary                  = sshBinary
        self.sshKeyGenBinary            = sshKeyGenBinary
        self.sshAgentBinary             = sshAgentBinary
        self.sshAddBinary               = sshAddBinary
        self.sshKeyScanBinary           = sshKeyScanBinary
        self.chownBinary                = chownBinary
        self.chmodBinary                = chmodBinary

        self.sshKeyPath                 = sshKeyPath
        self.sshKnownHosts              = sshKnownHosts

class KeyDist():

    def complete(self):
        returnval = self.completed.isSet()
        return returnval

    class passphraseDialog(wx.Dialog):

        def __init__(self, parent, id, title, text, okString, cancelString,helpString="Help! What is all this?"):
            #wx.Dialog.__init__(self, parent, id, pos=(200,150), style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER | wx.STAY_ON_TOP)
            wx.Dialog.__init__(self, parent, id, pos=(200,150), style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER)

            self.closedProgressDialog = False
            self.parent = parent
            if self.parent is not None and self.parent.__class__.__name__=="LauncherMainFrame":
                launcherMainFrame = parent
                if launcherMainFrame is not None and launcherMainFrame.progressDialog is not None:
                    launcherMainFrame.progressDialog.Show(False)
                    self.closedProgressDialog = True

            self.SetTitle(title)
            self.label = wx.StaticText(self, -1, text)
            self.PassphraseField = wx.TextCtrl(self, wx.ID_ANY,style=wx.TE_PASSWORD ^ wx.TE_PROCESS_ENTER)
            self.PassphraseField.SetFocus()
            self.canceled=True
            self.Cancel = wx.Button(self,-1,label=cancelString)
            self.OK = wx.Button(self,-1,label=okString)
            self.Help = wx.Button(self,-1,label=helpString)

            self.dataPanelSizer=wx.BoxSizer(wx.HORIZONTAL)
            self.dataPanelSizer.Add(self.label,flag=wx.ALL,border=5)
            self.dataPanelSizer.Add(self.PassphraseField,flag=wx.EXPAND|wx.ALL,border=5)

            self.buttonPanelSizer=wx.BoxSizer(wx.HORIZONTAL)
            self.buttonPanelSizer.Add(self.Cancel,0,wx.ALL,5)
            self.buttonPanelSizer.Add(self.Help,0,wx.ALL,5)
            self.buttonPanelSizer.AddStretchSpacer(prop=1)
            self.buttonPanelSizer.Add(self.OK,0,wx.ALL,5)

            self.sizer = wx.BoxSizer(wx.VERTICAL)
            self.sizer.Add(self.dataPanelSizer,flag=wx.EXPAND)
            self.sizer.Add(self.buttonPanelSizer,flag=wx.EXPAND)
            self.PassphraseField.Bind(wx.EVT_TEXT_ENTER,self.onEnter)
            self.OK.Bind(wx.EVT_BUTTON,self.onEnter)
            self.Cancel.Bind(wx.EVT_BUTTON,self.onEnter)
            self.Help.Bind(wx.EVT_BUTTON,self.onHelp)
#
            self.border = wx.BoxSizer(wx.VERTICAL)
            self.border.Add(self.sizer, 0, wx.EXPAND|wx.ALL, 15)
            self.CentreOnParent(wx.BOTH)
            self.SetSizer(self.border)
            self.Fit()

        def onEnter(self,e):
            self.canceled=True
            if (e.GetId() == self.Cancel.GetId()):
                logger_debug('onEnter: canceled = True')
                self.canceled = True
                self.password = None
            else:
                logger_debug('onEnter: canceled = False')
                self.canceled = False
                self.password = self.PassphraseField.GetValue()
            self.Close()

            if self.closedProgressDialog:
                if self.parent is not None and self.parent.__class__.__name__=="LauncherMainFrame":
                    launcherMainFrame = self.parent
                    if launcherMainFrame is not None and launcherMainFrame.progressDialog is not None:
                        launcherMainFrame.progressDialog.Show(True)
 
        def onHelp(self,e):
            from help.HelpController import helpController
            helpController.Display("Authentication Overview")
            #helpDialog = HelpDialog(self.GetParent(), title="MASSIVE/CVL Launcher", name="MASSIVE/CVL Launcher",pos=(200,150),size=(680,290),style=wx.STAY_ON_TOP)
            #helpPanel = wx.Panel(helpDialog)
            #helpPanelSizer = wx.FlexGridSizer()
            #helpPanel.SetSizer(helpPanelSizer)
            #helpText = wx.TextCtrl(helpPanel,wx.ID_ANY,value="",size=(400,400),style=wx.TE_READONLY|wx.TE_MULTILINE)
            #try:
                #helpText.LoadFile("sshHelpText.txt")
            #except:
                #pass
            #helpPanelSizer.Add(helpText,border=20,flag=wx.BORDER|wx.TOP|wx.RIGHT)
            #helpPanelSizer.Fit(helpPanel)
            #helpDialog.addPanel(helpPanel)
            #helpDialog.ShowModal()


        def getPassword(self):
            val = self.ShowModal()
            passwd = self.password
            canceled = self.canceled
            self.Destroy()
            return (canceled,passwd)

    class startAgentThread(Thread):
        def __init__(self,keydistObject):
            Thread.__init__(self)
            self.keydistObject = keydistObject
            self._stop = Event()

        def stop(self):
            self._stop.set()
        
        def stopped(self):
            return self._stop.isSet()


        def run(self):
            agentenv = None
            try:
                agentenv = os.environ['SSH_AUTH_SOCK']
            except:
                try:
                    agent = subprocess.Popen(self.keydistObject.sshpaths.sshAgentBinary,stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, universal_newlines=True)
                    stdout = agent.stdout.readlines()
                    for line in stdout:
                        if sys.platform.startswith('win'):
                            match = re.search("^SSH_AUTH_SOCK=(?P<socket>.*);.*$",line) # output from charade.exe doesn't match the regex, even though it looks the same!?
                        else:
                            match = re.search("^SSH_AUTH_SOCK=(?P<socket>.*); export SSH_AUTH_SOCK;$",line)
                        if match:
                            agentenv = match.group('socket')
                            os.environ['SSH_AUTH_SOCK'] = agentenv
                    if agent is None:
                        self.keydistObject.cancel(message="I tried to start an ssh agent, but failed with the error message %s"%str(stdout))
                        return
                except Exception as e:
                    self.keydistObject.cancel(message="I tried to start an ssh agent, but failed with the error message %s" % str(e))
                    return

            newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_GETPUBKEY,self.keydistObject)
            if (not self.stopped()):
                wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent)

    class genkeyThread(Thread):
        def __init__(self,keydistObject):
            Thread.__init__(self)
            self.keydistObject = keydistObject
            self._stop = Event()

        def stop(self):
            self._stop.set()
        
        def stopped(self):
            return self._stop.isSet()

        def run(self):
            logger_debug("genkeyThread: started")
            cmd = '{sshkeygen} -q -f "{keyfilename}" -C "{keycomment}" -N \"{password}\"'.format(sshkeygen=self.keydistObject.sshpaths.sshKeyGenBinary,
                                                                                                 keyfilename=self.keydistObject.sshpaths.sshKeyPath,
                                                                                                 keycomment=self.keydistObject.launcherKeyComment,
                                                                                                 password=self.keydistObject.password)
            try:
                keygen_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, universal_newlines=True)
                (stdout,stderr) = keygen_proc.communicate("\n\n")
                logger_debug("genkeyThread: sshkeygen completed")
                if (stderr != None):
                    logger_debug("genkeyThread: key gen proc returned an error %s"%stderr)
                    self.keydistObject.cancel("Unable to generate a new ssh key pair %s"%stderr)
                    return
                if (stdout != None):
                    logger_error("genkeyThread: key gen proc returned a message %s"%stdout)
                    #self.keydistObject.cancel("Unable to generate a new ssh key pair %s"%stderr)
                    #return
            except Exception as e:
                logger_debug("genkeyThread: sshkeygen threw an exception %s" % str(e))
                self.keydistObject.cancel("Unable to generate a new ssh key pair: %s" % str(e))
                return


            try:
                logger_debug("genkeyThread: sshkeygen completed, trying to open the key file")
                with open(self.keydistObject.sshpaths.sshKeyPath,'r'): pass
                event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_LOADKEY,self.keydistObject) # Auth hasn't really failed but this event will trigger loading the key
            except Exception as e:
                logger_error("genkeyThread: ssh key gen failed %s" % str(e))
                self.keydistObject.cancel("Unable to generate a new ssh key pair %s" % str(e))
                return
            if (not self.stopped()):
                logger_debug("genkeyThread: generating LOADKEY event from genkeyThread")
                wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),event)

    class getPubKeyThread(Thread):
        def __init__(self,keydistObject):
            Thread.__init__(self)
            self.keydistObject = keydistObject
            self._stop = Event()

        def stop(self):
            self._stop.set()
        
        def stopped(self):
            return self._stop.isSet()

        def run(self):
            threadid = threading.currentThread().ident
            logger_debug("getPubKeyThread %i: started"%threadid)
            sshKeyListCmd = self.keydistObject.sshpaths.sshAddBinary + " -L "
            logger_debug('getPubKeyThread: running command: ' + sshKeyListCmd)
            keylist = subprocess.Popen(sshKeyListCmd, stdout = subprocess.PIPE,stderr=subprocess.STDOUT,shell=True,universal_newlines=True)
            (stdout,stderr) = keylist.communicate()
            self.keydistObject.pubkeylock.acquire()

            logger_debug("getPubKeyThread %i: stdout of ssh-add -l: "%threadid + str(stdout))
            logger_debug("getPubKeyThread %i: stderr of ssh-add -l: "%threadid + str(stderr))

            lines = stdout.split('\n')
            logger_debug("getPubKeyThread %i: ssh key list completed"%threadid)
            for line in lines:
                match = re.search("^(?P<keytype>\S+)\ (?P<key>\S+)\ (?P<keycomment>.+)$",line)
                if match:
                    keycomment = match.group('keycomment')
                    correctKey = re.search('.*{launchercomment}.*'.format(launchercomment=self.keydistObject.launcherKeyComment),keycomment)
                    if correctKey:
                        self.keydistObject.keyloaded.set()
                        logger_debug("getPubKeyThread %i: loaded key successfully"%threadid)
                        self.keydistObject.pubkey = line.rstrip()
            logger_debug("getPubKeyThread %i: all lines processed"%threadid)
            if (self.keydistObject.keyloaded.isSet()):
                logger_debug("getPubKeyThread %i: key loaded"%threadid)
                logger_debug("getPubKeyThread %i: found a key, creating TESTAUTH event"%threadid)
                newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_TESTAUTH,self.keydistObject)
            else:
                logger_debug("getPubKeyThread %i: did not find a key, creating LOADKEY event"%threadid)
                newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_LOADKEY,self.keydistObject)
            self.keydistObject.pubkeylock.release()
            if (not self.stopped()):
                logger_debug("getPubKeyThread %i: is posting the next event"%threadid)
                wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent)
            logger_debug("getPubKeyThread %i: stopped"%threadid)

    class scanHostKeysThread(Thread):
        def __init__(self,keydistObject):
            Thread.__init__(self)
            self.keydistObject = keydistObject
            self.ssh_keygen_cmd = '{sshkeygen} -F {host} -f {known_hosts_file}'.format(sshkeygen=self.keydistObject.sshpaths.sshKeyGenBinary,host=self.keydistObject.host,known_hosts_file=self.keydistObject.sshpaths.sshKnownHosts)
            self.ssh_keyscan_cmd = '{sshscan} -H {host}'.format(sshscan=self.keydistObject.sshpaths.sshKeyScanBinary,host=self.keydistObject.host)
            self._stop = Event()

        def stop(self):
            self._stop.set()
        
        def stopped(self):
            return self._stop.isSet()

        def getKnownHostKeys(self):
            keygen = subprocess.Popen(self.ssh_keygen_cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True,universal_newlines=True)
            stdout,stderr = keygen.communicate()
            keygen.wait()
            hostkeys=[]
            for line in stdout.split('\n'):
                if (not (line.find('#')==0 or line == '')):
                    hostkeys.append(line)
            return hostkeys
                    
        def appendKey(self,key):
            with open(self.keydistObject.sshpaths.sshKnownHosts,'a+') as known_hosts:
                known_hosts.write(key)
                known_hosts.write('\n')
            

        def scanHost(self):
            scan = subprocess.Popen(self.ssh_keyscan_cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,shell=True,universal_newlines=True)
            stdout,stderr = scan.communicate()
            scan.wait()
            hostkeys=[]
            for line in stdout.split('\n'):
                if (not (line.find('#')==0 or line == '')):
                    hostkeys.append(line)
            return hostkeys

        def run(self):
            knownKeys = self.getKnownHostKeys()
            if (len(knownKeys)==0):
                hostKeys = self.scanHost()
                for key in hostKeys:
                    self.appendKey(key)
            newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEEDAGENT,self.keydistObject)
            if (not self.stopped()):
                wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent)
                        
            

    class testAuthThread(Thread):
        def __init__(self,keydistObject):
            Thread.__init__(self)
            self.keydistObject = keydistObject
            self._stop = Event()

        def stop(self):
            self._stop.set()
        
        def stopped(self):
            return self._stop.isSet()

        def run(self):
        
            # I have a problem where I have multiple identity files in my ~/.ssh, and I want to use only identities loaded into the agent
            # since openssh does not seem to have an option to use only an agent we have a workaround, 
            # by passing the -o IdentityFile option a path that does not exist, openssh can't use any other identities, and can only use the agent.
            # This is a little "racy" in that a tempfile with the same path could concievably be created between the unlink and openssh attempting to use it
            # but since the pub key is extracted from the agent not the identity file I can't see anyway an attacker could use this to trick a user into uploading the attackers key.
            threadid = threading.currentThread().ident
            logger_debug("testAuthThread %i: started"%threadid)
            import tempfile, os
            (fd,path)=tempfile.mkstemp()
            os.close(fd)
            os.unlink(path)
            
            ssh_cmd = '{sshbinary} -o IdentityFile={nonexistantpath} -o PasswordAuthentication=no -o PubkeyAuthentication=yes -o StrictHostKeyChecking=no -l {login} {host} echo "success_testauth"'.format(sshbinary=self.keydistObject.sshpaths.sshBinary,
                                                                                                                                                                                                             login=self.keydistObject.username,
                                                                                                                                                                                                             host=self.keydistObject.host,
                                                                                                                                                                                                             nonexistantpath=path)

            try:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
            except:
                # On non-Windows systems the previous block will die with 
                # "AttributeError: 'module' object has no attribute 'STARTUPINFO'" even though
                # the code is inside the 'if' block, hence the use of a dodgy try/except block.
                startupinfo = None

            logger_debug('testAuthThread: attempting: ' + ssh_cmd)
            ssh = subprocess.Popen(ssh_cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,shell=True,universal_newlines=True, startupinfo=startupinfo)
            stdout, stderr = ssh.communicate()
            ssh.wait()

            logger_debug("testAuthThread %i: stdout of ssh command: "%threadid + str(stdout))
            logger_debug("testAuthThread %i: stderr of ssh command: "%threadid + str(stderr))

            if 'success_testauth' in stdout:
                logger_debug("testAuthThread %i: got success_testauth in stdout :)"%threadid)
                self.keydistObject.authentication_success = True
                newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_AUTHSUCCESS,self.keydistObject)
            else:
                logger_debug("testAuthThread %i: did not see success_testauth in stdout, posting EVT_KEYDIST_AUTHFAIL event"%threadid)
                newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_AUTHFAIL,self.keydistObject)

            if (not self.stopped()):
                logger_debug("testAuthThread %i: self.stopped() == False, so posting event: "%threadid + str(newevent))
                wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent)
            logger_debug("testAuthThread %i: stopped"%threadid)


    class loadKeyThread(Thread):
        def __init__(self,keydistObject):
            Thread.__init__(self)
            self.keydistObject = keydistObject
            self._stop = Event()

        def stop(self):
            self._stop.set()
        
        def stopped(self):
            return self._stop.isSet()

        def run(self):
            from KeyModel import KeyModel
            threadid=threading.currentThread().ident
            threadname=threading.currentThread().name
            km = KeyModel(self.keydistObject.sshpaths.sshKeyPath)
            if (self.keydistObject.password!=None):
                password=self.keydistObject.password
                newevent1 = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_KEY_WRONGPASS, self.keydistObject)
            else:
                password=""
            newevent2 = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_KEY_LOCKED, self.keydistObject)
            incorrectCallback=lambda:wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent2)
            newevent3 = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_GETPUBKEY, self.keydistObject)
            loadedCallback=lambda:wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent3)
            newevent4 = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEWPASS_REQ,self.keydistObject)
            notFoundCallback=lambda:wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent4)
            newevent5 = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEEDAGENT,self.keydistObject)
            failedToConnectToAgentCallback=lambda:wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(),newevent5)
            km.addKeyToAgent(password,loadedCallback,incorrectCallback,notFoundCallback,failedToConnectToAgentCallback)


    class CopyIDThread(Thread):
        def __init__(self,keydist):
            Thread.__init__(self)
            self.keydistObject = keydist
            self._stop = Event()

        def stop(self):
            self._stop.set()
        
        def stopped(self):
            return self._stop.isSet()

        def run(self):
            sshClient = ssh.SSHClient()
            sshClient.set_missing_host_key_policy(ssh.AutoAddPolicy())
            try:
                sshClient.connect(hostname=self.keydistObject.host,username=self.keydistObject.username,password=self.keydistObject.password,allow_agent=False,look_for_keys=False)
                sshClient.exec_command("module load massive")
                sshClient.exec_command("/bin/mkdir -p ~/.ssh")
                sshClient.exec_command("/bin/chmod 700 ~/.ssh")
                sshClient.exec_command("/bin/touch ~/.ssh/authorized_keys")
                sshClient.exec_command("/bin/chmod 600 ~/.ssh/authorized_keys")
                sshClient.exec_command("/bin/echo \"%s\" >> ~/.ssh/authorized_keys"%self.keydistObject.pubkey)
                # FIXME The exec_commands above can fail if the user is over quota.
                sshClient.close()
                self.keydistObject.keycopied.set()
                event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_TESTAUTH,self.keydistObject)
                logger_debug('CopyIDThread: successfully copied the key')
            except socket.gaierror as e:
                logger_debug('CopyIDThread: socket.gaierror : ' + str(e))
                self.keydistObject.cancel(message=str(e))
                return
            except socket.error as e:
                logger_debug('CopyIDThread: socket.error : ' + str(e))
                self.keydistObject.cancel(message=str(e))
                return
            except ssh.AuthenticationException as e:
                logger_debug('CopyIDThread: ssh.AuthenticationException: ' + str(e))
                event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_COPYID_NEEDPASS,self.keydistObject,str(e))
            except ssh.SSHException as e:
                logger_debug('CopyIDThread: ssh.SSHException : ' + str(e))
                self.keydistObject.cancel(message=str(e))
                return
            if (not self.stopped()):
                wx.PostEvent(self.keydistObject.notifywindow.GetEventHandler(), event)



    class sshKeyDistEvent(wx.PyCommandEvent):
        def __init__(self,id,keydist,string=""):
            wx.PyCommandEvent.__init__(self,KeyDist.myEVT_CUSTOM_SSHKEYDIST,id)
            self.keydist = keydist
            self.string = string
            self.threadid = threading.currentThread().ident
            self.threadname = threading.currentThread().name

        def newkey(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_NEWPASS_REQ):
                logger_debug("received NEWPASS_REQ event")
                wx.CallAfter(event.keydist.getNewPassphrase_stage1,event.string)
            if (event.GetId() == KeyDist.EVT_KEYDIST_NEWPASS_RPT):
                logger_debug("received NEWPASS_RPT event")
                wx.CallAfter(event.keydist.getNewPassphrase_stage2)
            if (event.GetId() == KeyDist.EVT_KEYDIST_NEWPASS_COMPLETE):
                logger_debug("received NEWPASS_COMPLETE event")
                t = KeyDist.genkeyThread(event.keydist)
                t.setDaemon(True)
                t.start()
                event.keydist.threads.append(t)
            event.Skip()

        def copyid(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_COPYID_NEEDPASS):
                logger_debug("received COPYID_NEEDPASS event")
                wx.CallAfter(event.keydist.getLoginPassword,event.string)
            elif (event.GetId() == KeyDist.EVT_KEYDIST_COPYID):
                logger_debug("received COPYID event")
                t = KeyDist.CopyIDThread(event.keydist)
                t.setDaemon(True)
                t.start()
                event.keydist.threads.append(t)
            else:
                event.Skip()

        def scanhostkeys(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_SCANHOSTKEYS):
                logger_debug("received SCANHOSTKEYS event")
                t = KeyDist.scanHostKeysThread(event.keydist)
                t.setDaemon(True)
                t.start()
                event.keydist.threads.append(t)
            event.Skip()



        def shutdownEvent(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_SHUTDOWN):
                event.keydist.shutdownReal()
            else:
                skip()

        def cancel(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_CANCEL):
                event.keydist._canceled.set()
                event.keydist.shutdownReal()
                if (len(event.string)>0):
                    pass
                if (event.keydist.callback_fail != None):
                    event.keydist.callback_fail()
            else:
                event.Skip()

        def success(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_AUTHSUCCESS):
                logger_debug("received AUTHSUCCESS event")
                event.keydist.completed.set()
                if (event.keydist.callback_success != None):
                    event.keydist.callback_success()
            event.Skip()


        def needagent(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_NEEDAGENT):
                logger_debug("received NEEDAGENT event")
                t = KeyDist.startAgentThread(event.keydist)
                t.setDaemon(True)
                t.start()
                event.keydist.threads.append(t)
            else:
                event.Skip()

        def listpubkeys(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_GETPUBKEY):
                t = KeyDist.getPubKeyThread(event.keydist)
                t.setDaemon(True)
                t.start()
                logger_debug("received GETPUBKEY event from thread %i %s, starting thread %i %s in response"%(event.threadid,event.threadname,t.ident,t.name))
                event.keydist.threads.append(t)
            else:
                event.Skip()

        def testauth(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_TESTAUTH):
                t = KeyDist.testAuthThread(event.keydist)
                t.setDaemon(True)
                t.start()
                logger_debug("received TESTAUTH event from thread %i %s, starting thread %i %s in response"%(event.threadid,event.threadname,t.ident,t.name))
                event.keydist.threads.append(t)
            else:
                event.Skip()

        def keylocked(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_KEY_LOCKED):
                logger_debug("received KEY_LOCKED event")
                wx.CallAfter(event.keydist.GetKeyPassword)
            if (event.GetId() == KeyDist.EVT_KEYDIST_KEY_WRONGPASS):
                logger_debug("received KEY_WRONGPASS event")
                wx.CallAfter(event.keydist.GetKeyPassword,"Sorry, that passphrase was incorrect. ")
            event.Skip()

        def loadkey(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_LOADKEY):
                t = KeyDist.loadKeyThread(event.keydist)
                t.setDaemon(True)
                t.start()
                logger_debug("received LOADKEY event from thread %i %s, starting thread %i %s in response"%(event.threadid,event.threadname,t.ident,t.name))
                event.keydist.threads.append(t)
            else:
                event.Skip()

        def authfail(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_AUTHFAIL):
                if(not event.keydist.keyloaded.isSet()):
                    newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_LOADKEY,event.keydist)
                    wx.PostEvent(event.keydist.notifywindow.GetEventHandler(),newevent)
                else:
                    # if they key is loaded into the ssh agent, then authentication failed because the public key isn't on the server.
                    # *****TODO*****
                    # actually this might not be strictly true. gnome keychain (and possibly others) will report a key loaded even if its still locked
                    # we probably need a button that says "I can't remember my old key's passphrase, please generate a new keypair"
                    if (event.keydist.keycopied.isSet()):
                        newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_TESTAUTH,event.keydist)
                        logger_debug("received AUTHFAIL event from thread %i %s posting TESTAUTH event in response"%(event.threadid,event.threadname))
                        wx.PostEvent(event.keydist.notifywindow.GetEventHandler(),newevent)
                    else:
                        newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_COPYID_NEEDPASS,event.keydist)
                        logger_debug("received AUTHFAIL event from thread %i %s posting NEEDPASS event in response"%(event.threadid,event.threadname))
                        wx.PostEvent(event.keydist.notifywindow.GetEventHandler(),newevent)
            else:
                event.Skip()


        def startevent(event):
            if (event.GetId() == KeyDist.EVT_KEYDIST_START):
                logger_debug("received KEYDIST_START event")
                newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_SCANHOSTKEYS,event.keydist)
                wx.PostEvent(event.keydist.notifywindow.GetEventHandler(),newevent)
            else:
                event.Skip()

    myEVT_CUSTOM_SSHKEYDIST=None
    EVT_CUSTOM_SSHKEYDIST=None
    def __init__(self,parentWindow,username,host,notifywindow,sshPaths):
        KeyDist.myEVT_CUSTOM_SSHKEYDIST=wx.NewEventType()
        KeyDist.EVT_CUSTOM_SSHKEYDIST=wx.PyEventBinder(self.myEVT_CUSTOM_SSHKEYDIST,1)
        KeyDist.EVT_KEYDIST_START = wx.NewId()
        KeyDist.EVT_KEYDIST_CANCEL = wx.NewId()
        KeyDist.EVT_KEYDIST_SHUTDOWN = wx.NewId()
        KeyDist.EVT_KEYDIST_SUCCESS = wx.NewId()
        KeyDist.EVT_KEYDIST_NEEDAGENT = wx.NewId()
        KeyDist.EVT_KEYDIST_NEEDKEYS = wx.NewId()
        KeyDist.EVT_KEYDIST_GETPUBKEY = wx.NewId()
        KeyDist.EVT_KEYDIST_TESTAUTH = wx.NewId()
        KeyDist.EVT_KEYDIST_AUTHSUCCESS = wx.NewId()
        KeyDist.EVT_KEYDIST_AUTHFAIL = wx.NewId()
        KeyDist.EVT_KEYDIST_NEWPASS_REQ = wx.NewId()
        KeyDist.EVT_KEYDIST_NEWPASS_RPT = wx.NewId()
        KeyDist.EVT_KEYDIST_NEWPASS_COMPLETE = wx.NewId()
        KeyDist.EVT_KEYDIST_COPYID = wx.NewId()
        KeyDist.EVT_KEYDIST_COPYID_NEEDPASS = wx.NewId()
        KeyDist.EVT_KEYDIST_KEY_LOCKED = wx.NewId()
        KeyDist.EVT_KEYDIST_KEY_WRONGPASS = wx.NewId()
        KeyDist.EVT_KEYDIST_SCANHOSTKEYS = wx.NewId()
        KeyDist.EVT_KEYDIST_LOADKEY = wx.NewId()

        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.cancel)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.success)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.needagent)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.listpubkeys)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.testauth)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.authfail)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.startevent)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.newkey)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.copyid)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.keylocked)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.scanhostkeys)
        notifywindow.Bind(self.EVT_CUSTOM_SSHKEYDIST, KeyDist.sshKeyDistEvent.loadkey)

        self.completed=Event()
        self.parentWindow = parentWindow
        self.username = username
        self.host = host
        self.notifywindow = notifywindow
        self.sshKeyPath = ""
        self.threads=[]
        self.pubkeyfp = None
        self.keyloaded=Event()
        self.password = None
        self.pubkeylock = Lock()
        self.keycopied=Event()
        self.sshpaths=sshPaths
        self.launcherKeyComment=os.path.basename(self.sshpaths.sshKeyPath)
        self.authentication_success = False
        self.callback_success=None
        self.callback_fail=None
        self._canceled=Event()
        self.removeKey=Event()

    def GetKeyPassword(self,prepend=""):
        ppd = KeyDist.passphraseDialog(self.parentWindow,wx.ID_ANY,'Unlock Key',prepend+"Please enter the passphrase for the key","OK","Cancel")
        (canceled,passphrase) = ppd.getPassword()
        if (canceled):
            self.cancel("Sorry, I can't continue without the passphrase for that key. If you've forgotten the passphrase, you could remove the key and generate a new one. The key is probably located in ~/.ssh/MassiveLauncherKey*")
            return
        else:
            self.password = passphrase
            event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_TESTAUTH,self)
            wx.PostEvent(self.notifywindow.GetEventHandler(),event)

    def getLoginPassword(self,prepend=""):
        ppd = KeyDist.passphraseDialog(self.parentWindow,wx.ID_ANY,'Login Password',prepend+"Please enter your login password for username %s at %s"%(self.username,self.host),"OK","Cancel")
        (canceled,password) = ppd.getPassword()
        if canceled:
            self.cancel()
            return
        self.password = password
        event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_COPYID,self)
        wx.PostEvent(self.notifywindow.GetEventHandler(),event)

    def getNewPassphrase_stage1(self,prepend=""):
        ppd = KeyDist.passphraseDialog(self.parentWindow,wx.ID_ANY,'New Passphrase',prepend+"Please enter a new passphrase","OK","Cancel")
        (canceled,passphrase) = ppd.getPassword()
        if (not canceled):
            if (passphrase != None and len(passphrase) == 0):
                event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEWPASS_REQ,self,"Empty passphrases are forbidden. ")
            elif (passphrase != None and len(passphrase) < 6):
                event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEWPASS_REQ,self,"The passphrase was too short. ")
            else:
                self.password = passphrase
                event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEWPASS_RPT,self)
            wx.PostEvent(self.notifywindow.GetEventHandler(),event)
        else:
            self.cancel()

    def getNewPassphrase_stage2(self):
        ppd = KeyDist.passphraseDialog(self.parentWindow,wx.ID_ANY,'New Passphrase',"Please repeat the new passphrase","OK","Cancel")
        (canceled,phrase) = ppd.getPassword()
        if (phrase == None and not canceled):
            phrase = ""
        if (phrase == self.password):
            event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEWPASS_COMPLETE,self)
        else:
            event = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_NEWPASS_REQ,self,"The passphrases didn't match. ")
        wx.PostEvent(self.notifywindow.GetEventHandler(),event)


    def distributeKey(self,callback_success=None,callback_fail=None):
        event = KeyDist.sshKeyDistEvent(self.EVT_KEYDIST_START, self)
        wx.PostEvent(self.notifywindow.GetEventHandler(), event)
        self.callback_fail=callback_fail
        self.callback_success=callback_success
        
    def canceled(self):
        return self._canceled.isSet()

    def cancel(self,message=""):
        if (not self.canceled()):
            self._canceled.set()
            newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_CANCEL, self)
            logger_debug('Sending EVT_KEYDIST_CANCEL event.')
            wx.PostEvent(self.notifywindow.GetEventHandler(), newevent)

    def shutdownReal(self):
        if (self.removeKey.isSet()):
            pass
            #t=KeyDist.removeKeyFromAgentThread(event.keydist)
            #t.setDaemon(False)
            #t.start()
            #event.keydist.threads.append(t)
        for t in self.threads:
            try:
                t.stop()
                t.join()
            except:
                pass
        self.completed.set()

    def shutdown(self):
        if (not self.canceled()):
            newevent = KeyDist.sshKeyDistEvent(KeyDist.EVT_KEYDIST_SHUTDOWN, self)
            logger_debug('Sending EVT_KEYDIST_SHUTDOWN event.')
            wx.PostEvent(self.notifywindow.GetEventHandler(), newevent)
