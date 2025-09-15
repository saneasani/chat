import os
import tty
import time
import asyncio
from collections import deque
from asyncio import StreamReader, StreamWriter
from tools.manage_shell import *
from tools.message_store import MessageStore
from tools.custom_readers import create_stdin_reader, read_line



class Client:
    def __init__(self):
        self._username = None               # username name.
        self._messages = None               # store messages.
        self._key = "secret_key"            # for xor cryptography.
        self._process = None                # when browsing pc.
        
                                            # control main:
        self._writer = None                 # - writer.
        self._stdin_reader = None           # - reader.     
        self._control_tasks = {}            # - tasks.
        self._added_tasks = []

                                            # Control and store request of:
        self._send_file_tmp = {}            # - file sending.
        self._send_file_db = {}
        self._shell_control_tmp = {}        # - reverse shell.
        self._shell_control_db = {}



    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||Send/Receive file||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    """ Read/send file
    """    
    async def _read_file_name(self, stdin_reader, filename: list) -> int: 
        while True:
            try:
                await self._messages.append("[system] Write the file name here or type exit.\n")
                _filename  = await read_line(stdin_reader)
        
                if _filename == "exit":
                    filename[0]  = None
                    return 0 # error

                if os.path.isfile(_filename):
                    if os.path.getsize(_filename) > 2071611:
                        await self._messages.append("[system] File size maximum 1 gb.\n")
                    else:
                        filename[0] = _filename
                        return 1
                else:
                    await self._messages.append("[system] File doesn't exists or typo in name/path.\n")

            except Exception as e:
                await self._messages.append(f"[system] read file name errror: {e}.\n")
                return 0



    async def _send_file(self) -> None:
        writer = None
          
        try:
            if self._send_file_db.get("requester", 0):
                port = 8000 + int(self._send_file_db["requester"]["port"])
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                                                                
                sync_protocol = "[requester]"                     # send:
                await self._send_data(sync_protocol, writer)      # 1. protocol.
            
                file_name = self._send_file_db["requester"]["file_name"]
                with open(file_name, "r") as file_to_send:
                    file_send_buff = file_to_send.read()
                                       
                    await self._send_data(file_name, writer)      # 2. name of the file.
                    await self._send_data(file_send_buff, writer) # 3. file.

                    writer.close()
                    await writer.wait_closed()
                    writer = None


        except asyncio.exceptions.CancelledError:
            await self._messages.append(f"[system] Send file canceled.\n")
   
        except FileNotFoundError as e:
            await self._messages.append(f"[system] Send file error: File not found, error: {e}\n")

        except Exception as e:
            await self._messages.append(f"[system] Send file error, common error: {e}\n")
            
        finally:
            if self._send_file_db.get("requester", 0):
                del self._send_file_db["requester"]
                
            if writer is not None and port != 8000:
                writer.close()
                await writer.wait_closed()
            


    """ Open a connection to receive a file
    """ 
    async def _accept_file_name(self, reader: StreamReader) -> None:
        try:
            while (len_file_name := await asyncio.wait_for(reader.readline(), 25)) != b'':
                try:
                    len_file_name = int(len_file_name)
                
                    while (file_name := await asyncio.wait_for(reader.readexactly(len_file_name), 25)) != b'':
                        byte_array = file_name 
                        break
                    
                    if len_file_name == len(byte_array):
                        self._send_file_db["receiver"]["file_name_size"]= len_file_name
                        self._send_file_db["receiver"]["file_name"]= file_name
                        break
                    
                    else:
                       raise Exception("Something wrong with length.")

                except ValueError as e:
                    await self._messages.append(f"[system] Something wrong with parsing file name length, error: {e}\n")
                

        except asyncio.exceptions.CancelledError:
            pass

        except ConnectionError as e:
            await self._messages.append(f"[system] Connection lost while accepting file name from server, error:{e}\n") 
            
        except asyncio.exceptions.TimeoutError:
            await self._messages.append(f"[system] Accept file name error, didn't receive name of file.\n")
            self._send_file_db["receiver"]["file_name"] = False

        except Exception as e:
            await self._messages.append(f"[system] Accept file name error, common unknown error: {e}\n")
            self._send_file_db["receiver"]["file_name"] = False



    async def _open_to_rec_file(self) -> None:
        _time = 30
        writer = None
        
        try:
            if self._send_file_db.get("receiver", 0):
                port = 8000 + int(self._send_file_db["receiver"]["port"])         
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                
                sync_protocol = "[receiver]"
                await self._send_data(sync_protocol, writer)
                
                accept_file_name_task = asyncio.create_task(self._accept_file_name(reader))
                self._control_tasks["accept_file_name"] = accept_file_name_task
                self._added_tasks.append(accept_file_name_task)
                
                while (file_name := self._send_file_db["receiver"]["file_name"]) or _time:
                    if self._send_file_db["receiver"]["file_name"] == False:
                        raise Exception("Error with receiving file name")              
                       
                    if file_name:
                        while (file_size_bytes := await asyncio.wait_for(reader.readline(), 25)) != b'':
                            try:     
                                file_size = int(file_size_bytes)

                                while data := await asyncio.wait_for(reader.readexactly(file_size), 25):
                                    buffer = data
                                    break
                                
                                if len(buffer) > 2071611:
                                    raise Exception("File size is more than 1gb")

                                file_name_edited = None
                                                    
                                if file_size == len(buffer):
                                    self._send_file_db["receiver"]["file_name"] = self._xor_text(file_name.decode()).rstrip()
                                    self._send_file_db["receiver"]["file_size"] = file_size
                                    self._send_file_db["receiver"]["buffer"] = self._xor_text(buffer.decode())
                                    self._send_file_db["receiver"]["done"] = True

                                    file_name_edited = self._xor_text(file_name.decode()).rstrip()
                                    
                                else:
                                    raise Exception("Something wrong with receiving file size")
                                              
                                with open(f"[{time.strftime('%X %d %b %Y')}] Success file {file_name_edited} downloading from {self._username}.txt", "w") as file_write:
                                    file_write.write(self._send_file_db["receiver"]["buffer"])
                                    await self._messages.append(f"[system] {file_name_edited} from {self._send_file_db['receiver']['requester']} has been downloaded.\n")
                                    break
                                
                            except ValueError as e:
                                await self._messages.append(f"[system] Something wrong with parsing file name length while downloading file")
                                
                        break
                            
                    else:
                        await self._messages.append(f"[system] Waiting for connection with server for receiving file from {self._send_file_db['receiver']['requester']} - {_time}s.\n")
                        await asyncio.sleep(1)
                        
                        if _time % 3 == 0:           
                            writer.write(b'[ping]\n')
                            await writer.drain()
                                           
                        if not _time:
                            await self._messages.append(f"[system] Accept download from {self._send_file_db['receiver']['requester']}: time for waiting connection has been elapsed.\n")               
                            break

                        _time -= 1


        except asyncio.exceptions.TimeoutError:
            await self._messages.append("[system] Time for waiting file size or whole date elapsed.\n")

        except asyncio.exceptions.CancelledError:
            await self._messages.append("[system] Error, receiving file - canceled.\n")
              
        except ConnectionError as e:
            await self._messages.append(f"[system] Connection lost while file transfering, error: {e}\n")    

        except Exception as e:
            await self._messages.append(f"[system] Open to rec common, error: {e}\n")

        finally:          
            if self._control_tasks.get("accept_file_name", 0) and not self._control_tasks["accept_file_name"].done():
                self._control_tasks["accept_file_name"].cancel()
                await asyncio.sleep(1)

            if writer != None:     
                writer.close()
                await writer.wait_closed()

            if self._send_file_db.get("receiver", 0):
                del self._send_file_db["receiver"]



    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||Open/Control Shell|||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """


    async def _rec_ping_server_if_alive(self, dst_writer: StreamWriter) -> None:
        time  = 30
        
        try:
            while time:
                if time % 3 == 0:
                    dst_writer.write(b'[ping]\n')
                    await dst_writer.drain()

                await asyncio.sleep(1)
                time -= 1

                if not time:
                   time = 30

        except asyncio.exceptions.CancelledError:
            pass
            
        except ConnectionError as e:
            await self._messages.append(f"[system] Receiver ping server Connection error, error: {e}\n")

            if self._shell_control_db.get("receiver", 0):
                self._shell_control_db["receiver"]["flag_cancel"] = True

            if not self._control_tasks["shell_control"].done():
                self._control_tasks["shell_control"].cancel()
                await asyncio.sleep(1)
  
                
        except Exception as e: 
            await self._messages.append(f"[system] Receiver ping server common unknown error: {e}\n")
            if self._shell_control_db.get("receiver", 0):
                self._shell_control_db["receiver"]["flag_cancel"] = True
                
            if not self._control_tasks["shell_control"].done():
                self._control_tasks["shell_control"].cancel()
                await asyncio.sleep(1)
            


    """server will ping client to see if socket is alive, this function drops ping and save incoming data from
       reverse shell locally in buffer.
    """
    async def _scan_for_ping_n_store_info_in_buffer(self, reader: StreamReader) -> None:
        data = None
        
        try:
            while (data := await asyncio.wait_for(reader.readline(), 35)) != b'':
                if data == b"[ping]\n":
                    pass

                else:
                    try:
                        len_data = int(data)
                        while (data := await asyncio.wait_for(reader.readexactly(len_data), 9)) != b'':
                            byte_array = data
                            break
                        
                        if len_data == len(byte_array):
                            data = self._xor_text(byte_array.decode())
                            if self._shell_control_db.get("receiver", 0):
                                self._shell_control_db["receiver"]["buffer"].append(data)
                                
                        else:
                           raise Exception(f"Something wrong with length in scan/ping in buffer.") 

                      
                    except ValueError as e:
                        message = f"Error while converting length of message in scan/ping buffer, error: {e}\n"
                        raise Exception(message)
                        
                         
                    except Exception as e:
                        message = f"Error in receiving message in scan/ping buffer, error: {e}\n"
                        raise Exception(message)
            

        except Exception as e:
            await self._messages.append(f"[system] Scan and store error: {e} \n")
            if self._shell_control_db.get("receiver", 0):
                self._shell_control_db["receiver"]["flag_cancel"] = True

            if not self._control_tasks["shell_control"].done():
                self._control_tasks["shell_control"].cancel()
                await asyncio.sleep(1)

            

    async def _control_shell(self) -> None:
        writer = None
        file_name = None
        flag_listen = True
        data_flag = None
          
        try:
            await asyncio.sleep(1)
            if self._shell_control_db.get("receiver", 0):                                  
                port = 8000 + int(self._shell_control_db["receiver"]["port"])          
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                
                sync_protocol = "[receiver]"
                await self._send_data(sync_protocol, writer)

                _deque = deque(maxlen=255)
                self._shell_control_db["receiver"]["buffer"] = _deque
                
                rec_ping_server = asyncio.create_task(self._rec_ping_server_if_alive(writer))
                self._control_tasks["rc_png_srvr"] = rec_ping_server
                self._added_tasks.append(rec_ping_server)

                scan_n_store_task = asyncio.create_task(self._scan_for_ping_n_store_info_in_buffer(reader))
                self._control_tasks["scan_n_store"] = scan_n_store_task
                self._added_tasks.append(scan_n_store_task)
                
                  
                await self._messages.append("[system] Start to write commands.\n")
                
                while (data_out := await asyncio.wait_for(read_line(self._stdin_reader), 333)) != b'':
                    await self._send_data(data_out, writer)
                    sys.stdout.flush()
                    
                    if data_out == "exit":
                        self._control_tasks["rc_png_srvr"].cancel()
                        await asyncio.sleep(1)
                        break

                    time = 5
                    
                    while time:
                    
                        await asyncio.sleep(1)
                        time -= 1
      
                        if not len(_deque):
                            continue
                       
                        if (data_in := self._shell_control_db["receiver"]["buffer"].popleft()):
                            await self._messages.append(f"[reverse_shell_result] {data_in.rstrip()}\n")
                            data_flag = True # received data.
                            break
    
                    if data_flag:
                        continue
                    
                    if not time:
                        await self._messages.append("[system] No information from other side, canceling reverse shell.\n")
                        break


        except asyncio.exceptions.CancelledError:
            await self._messages.append("[system] Cancelled: reverse shell.\n")
            
            if self._shell_control_db["receiver"].get("flag_cancel", 0) and self._shell_control_db["receiver"]["flag_cancel"]:
                flag_listen = True
            else:
                flag_listen = False
                    
        except asyncio.exceptions.TimeoutError:
            await self._messages.append("[system] Time for waiting from you message elapsed, canceling reverse shell, switching back to chat.\n")
            flag_listen = True
                    
        except Exception as e:
            await self._messages.append(f"[system] Something wrong with control shell, canceling reverse shell, switching back to chat, Error: {e}\n")
            flag_listen = True

        finally:
            if self._shell_control_db.get("receiver", 0):
                del self._shell_control_db["receiver"]
            
            if flag_listen and self._control_tasks["input_listener"].done():
                input_listener = asyncio.create_task(self._read_and_send_messages(self._stdin_reader, self._writer))
                self._added_tasks.append(input_listener)
                self._control_tasks["input_listener"] = input_listener
                await self._messages.append("[system] Switching back to chat.\n")

            if self._control_tasks.get("rc_png_srvr", 0):
                self._control_tasks["rc_png_srvr"].cancel()
                await asyncio.sleep(1)

            if writer != None:
                writer.close()
                await writer.wait_closed()

            if self._control_tasks.get("scan_n_store", 0):
                self._control_tasks["scan_n_store"].cancel()
                await asyncio.sleep(1)



    async def _open_shell(self) -> None:   
        writer = None
        flag_exit = False
        data = None
          
        try:
            if self._shell_control_db.get("requester", 0):
                
                port = 8000 + int(self._shell_control_db["requester"]["port"])
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                
                sync_protocol = "[requester]"
                await self._send_data(sync_protocol, writer)
              
                self._process = await asyncio.create_subprocess_shell(
                    '/bin/bash',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,
                )

                
                while (data := await asyncio.wait_for(reader.readline(), 33)) != b'':
                    if data == b"[ping]\n": # check if socket alive.
                        continue

                    else:
                        try:
                            len_data = int(data)
                            while (data := await asyncio.wait_for(reader.readexactly(len_data), 9)) != b'':
                                byte_array = data
                                break
                            
                            if len_data == len(byte_array):
                                data = self._xor_text(byte_array.decode()).encode()
                        
                                # stdin
                                self._process.stdin.write(data) # shell command from other side of connection.
                  
                                if data == b'exit\n':
                                    flag_exit = True                 
                                
                                # stdout     
                                stdout_buf = bytearray(b'')
                                out_read = await self._browser_read_from_pipe(self._process.stdout, stdout_buf, 0.1)

                                if out_read > 1028:
                                    out_read_message = f"Output has more than 1028 characters, can't proceed, from command: {data.decode()}"
                                else:             
                                    out_read_message = await self._clear_carriage_return(stdout_buf, out_read) if out_read else None

                                if out_read_message: # user that provides shell will see also stdout from reverse shell.
                                    await self._messages.append(f"[system][r_shell] {out_read_message.rstrip()}.\n")
                                    await self._send_data(out_read_message, writer) 

                                # stderr
                                stderr_buf = bytearray(b'')
                                err_read = await self._browser_read_from_pipe(self._process.stderr, stderr_buf, 0.1)
                            
                                if err_read > 1028:
                                    err_read_message= f"Output error has more than 1028 characters, can't proceed, from command: {data.decode()}"
                                else:             
                                    err_read_message = await self._clear_carriage_return(stderr_buf, err_read) if err_read else None
                       
                                if err_read_message: # user that provides shell will see also stderr from reverse shell.
                                    await self._messages.append(f"[system][r_shell] {err_read_message.rstrip()}.\n")
                                    await self._send_data(err_read_message, writer) 

                                if out_read_message == None and err_read_message == None:
                                    await self._send_data("None.", writer)
                                
                                if self._process.returncode is not None:
                                    if flag_exit:
                                        await self._messages.append(f"[system][r_shell] Closing reverse shell, other side closed connection, returned code:{self._process.returncode}.\n")
                                    else:
                                        await self._messages.append(f"[system][r_shell] Closing reverse shell, returned code:{self._process.returncode}.\n")
                                    self._process = None
                                    break

                            else:
                                raise Exception(f"Something wrong with length in scan/ping in buffer.") 

                      
                        except ValueError as e:
                            await self._messages.append(f"[system] Error while converting length of message in open shell, error: {e}\n")
                            break
                                     
                        except Exception as e:
                            await self._messages.append(f"[system] Error in receiving message in open shell, error: {e}\n")
                            break

                            
        except asyncio.exceptions.CancelledError:
            await self._messages.append(f"[system] Cancelled: open shell.\n")
            if self._process:
                self._process.stdin.write(b'exit\n')
                self._process = None

        except asyncio.exceptions.TimeoutError:
            await self._messages.append("[system] Time for waiting on open shell elapsed, canceling.\n")
            if self._process:
                self._process.stdin.write(b'exit\n')
                self._process = None
                   
        except Exception as e:
             await self._messages.append(f"[system] Common error open shell, error: {e}\n")
             if self._process:
                 self._process.stdin.write(b'exit\n')
                 self._process = None

        finally:
            if self._shell_control_db.get("requester", 0):
                del self._shell_control_db["requester"]
            await self._messages.append(f"[system] Reverse shell closed.\n")
            if writer != None:
                writer.close()
                await writer.wait_closed()



                

    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||||Browse PC||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    async def _browser_read_from_pipe(self, pipe, buf, timeout_sec: int) -> int:
        try:
            while True:
                try:
                    pipe_byte = await asyncio.wait_for(pipe.read(1), timeout_sec)
                except asyncio.TimeoutError:
                    return len(buf)     # no more bytes available currently on that pipe
                else:
                    if len(pipe_byte) == 1:
                        buf.append(pipe_byte[0])
                    else:
                        return len(buf) # end of pipe reached
                    
        except Exception as e:
             await self._messages.append(f"[system] Browser read from pipe error: {e}\n")



    async def _browser_read_from_input(self, pipe, stdin_reader, stdin_buf: list) -> None:
        try:
            message = await read_line(stdin_reader)
            the_input = message + '\n'
            the_input = the_input.encode()
            stdin_buf[0] = the_input
            pipe.write(the_input)
            
            await pipe.drain()
            
        except Exception as e:
             await self._messages.append(f"[system] Browser read from input: {e}\n")



    async def _browser(self, stdin_reader) -> int:
        stdin_buf = [None]
        try:        
            self._process = await asyncio.create_subprocess_shell(
                '/bin/bash',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )
           
            while True:
                await self._messages.append("[system] =========Browse local pc data===============\n")
                # stdin
                await self._browser_read_from_input(self._process.stdin, stdin_reader, stdin_buf)
                if stdin_buf[0] == b'exit\n':
                    break

                # stdout
                stdout_buf = bytearray(b'')           
                out_read = await self._browser_read_from_pipe(self._process.stdout, stdout_buf, 0.1)
                await self._messages.append(f'stdout[{out_read}]: {stdout_buf.decode("ascii")}\n') if out_read else None

                # stderr
                stderr_buf = bytearray(b'')             
                err_read = await self._browser_read_from_pipe(self._process.stderr, stderr_buf, 0.1)
                await self._messages.append(f'stderr[{err_read}]: {stderr_buf.decode("ascii")}\n') if err_read else None

            if self._process.returncode is not None:
                sys.stdout.flush()
                return_code= self._process.returncode
                self._process = None
                return self._process.returncode

        except Exception as e:
            await self._messages.append(f"[system] Browser error: {e}\n")

            if self._process:
                self._process.stdin.write(b'exit')
                self._process = None

        await self._messages.append("[system] Entering back to chat.\n")





    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||||Common tools|||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    def _xor_text(self, text: str) -> str:
        return ''.join(chr(ord(x) ^ ord(y)) for x, y in zip(text, self._key * (len(text) // len(self._key)) + self._key[:len(text) % len(self._key)]))
          


    async def _clear_carriage_return(self, text_byte: bytearray, length: int) -> str:
        try:
            edited_array = ""
            i = 0

            while i <= length:
                if i == length:
                    edited_array += '\n'
                    break

                elif text_byte[i] in [9, 10]:
                     edited_array += ' '

                else:
                    edited_array += chr(text_byte[i])
                    
                i += 1

            return edited_array

        except Exception as e:
            await self._messages.append(f"[system] Clear carriage return unknown error: {e}\n") 



    async def _wait_participant_to_accept(self, flag_req_or_rec: str, purpose: str) -> None:
        # purpose can be: sending file, shell.
        if purpose == "s_file":
            purpose = "sending file"
            
        time = 10
        message = ""

        try:
            while time:
                if purpose == "sending file":    
                    if self._send_file_tmp[f"{flag_req_or_rec}"]["token"]:  #  accepted the connection.
                        if self._send_file_tmp[f"{flag_req_or_rec}"]["port"]:
                            port_num = self._send_file_tmp[f"{flag_req_or_rec}"]["port"]
                            
                            if flag_req_or_rec == "requester":
                                self._send_file_db[f"{flag_req_or_rec}"] = {}
                                self._send_file_db[f"{flag_req_or_rec}"] = self._send_file_tmp[f"{flag_req_or_rec}"].copy()
                                
                                send_file_task = asyncio.create_task(self._send_file())
                                self._control_tasks["send_file"] = send_file_task
                                self._added_tasks.append(send_file_task)
                                
                                await self._messages.append(f"[system] Sending file activated, please wait.\n")
                                break
                            
                            else: # receiver
                                self._send_file_db[f"{flag_req_or_rec}"] = {}
                                self._send_file_db[f"{flag_req_or_rec}"] = self._send_file_tmp[f"{flag_req_or_rec}"].copy()

                                open_rec_file_task = asyncio.create_task(self._open_to_rec_file())
                                self._control_tasks["open_rec_file"] = open_rec_file_task
                                self._added_tasks.append(open_rec_file_task)
                        
                                await self._messages.append(f"[system] Sending file activated, please wait.\n")
                                break
                        else:
                            raise Exception("File sending error, missing port.\n")

                    
                elif purpose == "shell":
                    if self._shell_control_tmp[f"{flag_req_or_rec}"]["token"]:
                        if flag_req_or_rec == "requester":
                            self._shell_control_db[f"{flag_req_or_rec}"] = {}
                            self._shell_control_db[f"{flag_req_or_rec}"] = self._shell_control_tmp[f"{flag_req_or_rec}"].copy()
                            del self._shell_control_tmp[f"{flag_req_or_rec}"]

                            shell_open_task = asyncio.create_task(self._open_shell())
                            self._added_tasks.append(shell_open_task)
                            self._control_tasks["shell_open"] = shell_open_task

                            await self._messages.append(f"[system] Reverse shell activated, other side will have access to your shell.\n")
                            await self._messages.append(f"[system] Remember you always can cancel by entering: ~.\n")
                            break
                        
                        else: # receiver
                            self._shell_control_db[f"{flag_req_or_rec}"] = {}
                            self._shell_control_db[f"{flag_req_or_rec}"] = self._shell_control_tmp[f"{flag_req_or_rec}"].copy()
                            del self._shell_control_tmp[f"{flag_req_or_rec}"]
                            
                            shell_contol_task = asyncio.create_task(self._control_shell())
                            self._control_tasks["shell_control"] = shell_contol_task                  
                            self._control_tasks["input_listener"].cancel()
    
                            self._added_tasks.append(shell_contol_task)
                            await self._messages.append(f"[system] Switching to reverse shell. Please wait.\n")    
                            break

                await asyncio.sleep(1)
                time-=1
                
            
        except asyncio.exceptions.CancelledError:
            await self._messages.append(f"[system] Cancelled: {purpose}.\n")


        except Exception as e:
            await self._messages.append(f"[system] Common error, scope: {purpose}, error: {e}\n")
            if purpose == "sending file":
                if self._send_file_tmp.get(f"{flag_req_or_rec}", 0):
                    del self._send_file_tmp[f"{flag_req_or_rec}"]
                if self._send_file_db.get(f"{flag_req_or_rec}", 0):
                    del self._send_file_db[f"{flag_req_or_rec}"]
                    
            elif purpose == "shell":
                if self._shell_control_tmp.get(f"{flag_req_or_rec}", 0):   
                    del self._shell_control_tmp[f"{flag_req_or_rec}"]
                if self._shell_control_db.get(f"{flag_req_or_rec}", 0):
                    del self._shell_control_db[f"{flag_req_or_rec}"]



    def _extract_data_from_message(self, data_in: str, action = None) -> str:    
        idx = 0
        data_out = ""

        if data_in.startswith("[system][protocol_shell]"):
            if action == "port":    
                idx = 24
            elif action == "req_or_rec":
                idx = 27
            elif action == "requester":
                idx = 38
            elif action == "receiver":
                idx = 37

        elif data_in.startswith("[system][protocol_s_file]"):
            if action == "port":    
                idx = 25
            elif action == "req_or_rec":
                idx = 28
            elif action == "requester":
                idx = 39
            elif action == "receiver":
                idx = 38
        
        elif data_in.startswith("[system][protocol]"):
            if action == "port":    
                idx = 18             
            elif action == "req_or_rec":
                idx = 21
            elif action == "requester":
                idx = 32
            elif action == "receiver":
                idx = 31

        elif data_in.startswith("[send_file][ok]"):
            idx = 15   
        elif data_in.startswith("[send_file]"):
            idx = 11
            
        elif data_in.startswith("[r_shell][ok]"):
            idx = 13    
        elif data_in.startswith("[r_shell]"):
            idx = 9

        if data_in[idx] == "[":
            for el in data_in[idx+1::]:
                if el == "]":
                  data_out += el
                  break
                elif el != "]":
                  data_out += el

            if data_out[-1] != "]":
               return 0 # error

            else:
              data_out = data_out[:-1]
              
        return data_out



    async def _activate_send_file_or_shell(self, req_or_rec: str, port: str, db_control: str) -> None:
        try: 
            if db_control == "file_send":
                self._send_file_tmp[f"{req_or_rec}"]["token"] = True
                self._send_file_tmp[f"{req_or_rec}"]["port"] = port

            elif db_control == "shell":
                self._shell_control_tmp[f"{req_or_rec}"]["token"] = True
                self._shell_control_tmp[f"{req_or_rec}"]["port"] = port
                
        except Exception as e:
            await self._messages.append(f"[system] Activate send file common error: {e}\n")





  
    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||Read/send messages|||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||||||||Main|||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """ 

    # Receive messages/protocols from server[chat/system]
    async def _listen_for_messages(self, reader: StreamReader) -> None:
        len_msg = None
        try:
            
            while (message := await reader.readline()) != b'':
                message = message.decode()
                
                if message == "[ping]\n": # server pings client
                    pass

                else:
                    try:
                        len_msg = int(message)   # b'123', when receiving length of message.
                        while (message := await asyncio.wait_for(reader.readexactly(len_msg), 9)) != b'':      
                            byte_array = message # receiving message
                            break
                        
                        if len_msg == len(byte_array):
                            message = self._xor_text(byte_array.decode())
                        else:
                           raise Exception(f"Something wrong with length.")


                        # handle data for receiving/sending a file: 
                        if message.startswith("[system][protocol_s_file]"):
                            check =  self._extract_data_from_message(message, "port")

                            if check == "cancel":
                                if self._send_file_db.get("requester", 0):
                                    self._control_tasks["send_file"].cancel()
                                    await asyncio.sleep(1)
                                elif self._send_file_db.get("receiver", 0):
                                    self._control_tasks["open_rec_file"].cancel()
                                    await asyncio.sleep(1)
                            
                                if self._control_tasks.get("wait_s_file_req", 0):
                                    self._control_tasks["wait_s_file_req"].cancel()
                                    await asyncio.sleep(1)
                                elif self._control_tasks.get("wait_s_file_rec", 0):
                                    self._control_tasks["wait_s_file_rec"].cancel()
                                    await asyncio.sleep(1)
                    
                            else:
                                req_or_rec = self._extract_data_from_message(message, "req_or_rec")
                               
                                if req_or_rec == "receiver": 
                                    checked_name = self._extract_data_from_message(message, "receiver")

                                    if self._send_file_tmp.get("receiver", 0) and self._send_file_tmp["receiver"].get("requester", 0):
                                        checked_name == self._send_file_tmp["receiver"].get("requester", 0)
                                        port = self._extract_data_from_message(message, "port")
                                        await self._activate_send_file_or_shell("receiver", port, "file_send")                

                                elif req_or_rec == "requester":
                                    checked_name = self._extract_data_from_message(message, "requester")
                                    
                                    if self._send_file_tmp.get("requester", 0) and self._send_file_tmp["requester"].get("receiver", 0):
                                        checked_name == self._send_file_tmp["requester"].get("receiver", 0)
                                        port = self._extract_data_from_message(message, "port")
                                        await self._activate_send_file_or_shell("requester", port, "file_send")  



                        # handle data for provide/take a shell controlling:
                        elif message.startswith("[system][protocol_shell]"):               
                            check =  self._extract_data_from_message(message, "port")

                            if check == "rqcancel":
                                if self._shell_control_db.get("requester", 0) and self._control_tasks.get("shell_open", 0) and \
                                   not self._control_tasks["shell_open"].done():            
                                    self._control_tasks["shell_open"].cancel()
                                    await asyncio.sleep(1)

                                if self._control_tasks.get("wait_shell_req", 0) and self._control_tasks.get("wait_shell_req", 0) and \
                                   not self._control_tasks["wait_shell_req"].done():
                                    self._control_tasks["wait_shell_req"].cancel()
                                    await asyncio.sleep(1)


                            elif check == "rccancel":
                                if self._shell_control_db.get("receiver", 0):
                                    self._shell_control_db["receiver"]["flag_cancel"] = True
                                    if self._control_tasks.get("shell_control", 0) and not self._control_tasks["shell_control"].done():
                                        self._control_tasks["shell_control"].cancel()
                                        await asyncio.sleep(1)

                                    
                                if self._control_tasks.get("wait_shell_rec", 0) and not self._control_tasks["wait_shell_rec"].done():
                                    self._control_tasks["wait_shell_rec"].cancel()
                                    await asyncio.sleep(1)


                            else: # success - activate connection with server:                      
                                req_or_rec = self._extract_data_from_message(message, "req_or_rec")
                                if req_or_rec == "receiver":
                                    checked_name = self._extract_data_from_message(message, "receiver")

                                    if self._shell_control_tmp.get("receiver", 0) and self._shell_control_tmp["receiver"].get("requester", 0):
                                        if checked_name ==  self._shell_control_tmp["receiver"].get("requester", 0):
                                            port = self._extract_data_from_message(message, "port")
                                            await self._activate_send_file_or_shell("receiver", port, "shell")
                       
                                elif req_or_rec == "requester":
                                    checked_name = self._extract_data_from_message(message, "requester")

                                    if self._shell_control_tmp.get("requester", 0) and self._shell_control_tmp["requester"].get("receiver", 0): 
                                        if checked_name == self._shell_control_tmp["requester"].get("receiver", 0):
                                            port = self._extract_data_from_message(message, "port")
                                            await self._activate_send_file_or_shell("requester", port, "shell")

                        else:
                            await self._messages.append(message)

                        
                    except ValueError as e:
                        await self._messages.append(f"[system] Error while converting length of message, error: {e}\n")
                        
                         
                    except Exception as e:
                        await self._messages.append(f"[system] Error in receiving message in listen for messages, error: {e}\n")
            

            await self._messages.append("[system] Server closed connection.\n")
            await self._clear_all_tasks()
            self._messages._deque.clear()

   
        except Exception as e:
            await self._messages.append(f"[system] Listen error: {e}\n")
            await self._clear_all_tasks()

            

    async def _clear_all_tasks(self) -> None:
        try:
            for el in self._added_tasks:
                if not el.done():
                    el.cancel()

            if self._process:
                self._process.stdin.write(b'exit')
                self._process = None
                
            await self._messages.append("[system] Force quit.\n")

        except Exception as e:
            await self._messages.append(f"[system] Clear all tasks common error: {e}\n")


    # Send data:
    async def _send_data(self, data: str, writer: StreamWriter) -> None:
        try:
            data += '\n'
            xor_msg = self._xor_text(data)      
            len_msg = len(data)        
            writer.write((str(len_msg)  + '\n').encode())
            writer.write((xor_msg).encode())
            await writer.drain()

        except Exception as e:
            await self._messages.append(f"[system] Send data: {data}, error: {e}\n")
            

    # Read-send  message to chat/activate commands locally.
    async def _read_and_send_messages(self, stdin_reader: StreamReader, writer: StreamWriter) -> None:
        try:
            while True:              
                message =  await asyncio.wait_for(read_line(stdin_reader), 333)      
                if message == "~": # force quit from reverse shell:
                    if self._control_tasks.get("shell_open", 0):
                        self._control_tasks["shell_open"].cancel()
                        await asyncio.sleep(1)

                elif message == "[clear]": # clear messages.
                    clear_screen()
                    sys.stdout.flush()
                    self._messages._deque.clear()
                    
                                       
                elif message == "[help]": # show commands
                    await self._messages.append("[system] - Send file.\n")
                    await self._messages.append("[system] [send_file][here_should_be_receiver_username]\n")
                    await self._messages.append("[system] [send_file][ok][here_should_be_requester_username]\n")
                    await self._messages.append("[system] - Private chat.\n")
                    await self._messages.append("[system] [p][here_should_be_receiver_username]\n")
                    await self._messages.append("[system] [p][ok][here_should_be_requester_username]\n")
                    await self._messages.append("[system] - Reverse shell.\n")
                    await self._messages.append("[system] [r_shell][here_should_be_receiver_username]\n")
                    await self._messages.append("[system] [r_shell][ok][here_should_be_requester_username]\n")
                    await self._messages.append("[system] - Show online.\n")
                    await self._messages.append("[system] [online]\n")
                    await self._messages.append("[system] - Ban user.\n")
                    await self._messages.append("[system] [ban][target_username]\n")
                    await self._messages.append("[system] [unban][target_username]\n") 
                    sys.stdout.flush()
   
        
                elif message.startswith("[browser]"): # browse pc
                    return_code = await self._browser(stdin_reader)


                elif message.startswith("[send_file][ok]"):
                    await self._send_data(message, writer)
                    sys.stdout.flush()
                    
                          
                    requester_name = self._extract_data_from_message(message)
                    receiver_name = self._username
     
                    self._send_file_tmp["receiver"] = {}
                    self._send_file_tmp["receiver"]["receiver"] = receiver_name
                    self._send_file_tmp["receiver"]["requester"] = requester_name    
                    self._send_file_tmp["receiver"]["file_name"] = None
                    self._send_file_tmp["receiver"]["port"] = -1
                    self._send_file_tmp["receiver"]["token"] = False
                    self._send_file_tmp["receiver"]["done"] = False
                
                    wait_s_file_rec = asyncio.create_task(self._wait_participant_to_accept("receiver", "s_file"))
                    self._added_tasks.append(wait_s_file_rec)
                    self._control_tasks["wait_s_file_rec"] = wait_s_file_rec
                    

                elif message.startswith("[send_file]"):       
                    receiver_name = self._extract_data_from_message(message)
                    sys.stdout.flush()

                    file_name = [None]

                    # read file name.        
                    return_code = await self._read_file_name(stdin_reader, file_name) 
                    
                    # for tests to avoid each writing file name.
##                    file_name[0] = "test.py"
##                    return_code = 1 
           
                    if return_code:
                        await self._send_data(f"[send_file][{receiver_name}]", writer)
                        
        
                        self._send_file_tmp["requester"] = {}
                        self._send_file_tmp["requester"]["requester"] = self._username
                        self._send_file_tmp["requester"]["receiver"] = receiver_name
                        self._send_file_tmp["requester"]["file_name"] = file_name[0]
                        self._send_file_tmp["requester"]["port"]= -1
                        self._send_file_tmp["requester"]["token"]= False

                        wait_s_file_req = asyncio.create_task(self._wait_participant_to_accept("requester", "s_file"))
                        self._added_tasks.append(wait_s_file_req)
                        self._control_tasks["wait_s_file_req"] = wait_s_file_req
                            
                    else:
                        await self._messages.append("[system] Entered back to the chat.\n")


                elif message.startswith("[r_shell][ok]"):
                    requester_name = self._extract_data_from_message(message)
                    receiver_name = self._username
                    await self._send_data(message, writer)
                    sys.stdout.flush()

                    self._shell_control_tmp["receiver"] = {}
                    self._shell_control_tmp["receiver"]["receiver"] = receiver_name
                    self._shell_control_tmp["receiver"]["requester"] = requester_name    
                    self._shell_control_tmp["receiver"]["port"] = -1
                    self._shell_control_tmp["receiver"]["token"] = False

                    wait_shell_req = asyncio.create_task(self._wait_participant_to_accept("receiver", "shell"))
                    self._added_tasks.append(wait_shell_req)
                    self._control_tasks["wait_shell_rec"] = wait_shell_req


                elif message.startswith("[r_shell]"):
                    receiver_name = self._extract_data_from_message(message)
        
                    await self._send_data(f"[r_shell][{receiver_name}]", writer)
                    sys.stdout.flush()

                    self._shell_control_tmp["requester"] = {}
                    self._shell_control_tmp["requester"]["requester"] = receiver_name
                    self._shell_control_tmp["requester"]["receiver"] = receiver_name
                    self._shell_control_tmp["requester"]["port"]= -1
                    self._shell_control_tmp["requester"]["token"]= False

                    wait_shell_rec = asyncio.create_task(self._wait_participant_to_accept("requester", "shell"))
                    self._added_tasks.append(wait_shell_rec)
                    self._control_tasks["wait_shell_req"] = wait_shell_rec
       
                else:
                    await self._send_data(message, writer)
                    sys.stdout.flush()
            
        except asyncio.exceptions.CancelledError:
            pass

        except asyncio.exceptions.TimeoutError:
            pass
   
        except Exception as e:
            await self._messages.append(f"[system] Read and send message blocked, use Ctrl-C for exit, error: {e}\n")


    # All tasks here:
    async def _main(self, reader: StreamReader, writer: StreamWriter, stdin_reader) -> None:
        self._control_tasks = None
        try:
            self._writer = writer
            message_listener = asyncio.create_task(self._listen_for_messages(reader))  
            input_listener = asyncio.create_task(self._read_and_send_messages(stdin_reader, self._writer))
            
            self._added_tasks.extend([message_listener, input_listener])
            self._control_tasks = {"message_listener": message_listener,
                                    "input_listener" : input_listener}
            
            await asyncio.gather(*self._added_tasks)

        except asyncio.exceptions.CancelledError:
            await self._clear_all_tasks()


        except Exception as e:
            await self._messages.append(f"[system] Common main error: {e}\n")

        self._messages._deque.clear()




if __name__ == "__main__":
    async def start() -> None:
        async def redraw_output(items: deque) -> None:
            save_cursor_position()
            move_to_top_of_screen()
            for item in items:
                delete_line()
                sys.stdout.write(item)
            restore_cursor_position()

        tty.setcbreak(0)
        os.system('clear')
        rows = move_to_bottom_of_screen()

        chat_client = Client()
        chat_client._messages = MessageStore(redraw_output, rows - 1)
        

        chat_client._stdin_reader = await create_stdin_reader()
        sys.stdout.write("Enter username: ")
        chat_client._username = await read_line(chat_client._stdin_reader)


        reader, writer = await asyncio.open_connection("127.0.0.1", 8000)
        await chat_client._send_data(chat_client._username, writer)

      
        try:
            await chat_client._main(reader, writer, chat_client._stdin_reader)
            
        except Exception as e:
            print(f"[system] Common start error:", e)
            writer.close()
            await writer.wait_closed()


    try:   
        asyncio.run(start())


    except KeyboardInterrupt:
        print("Have a nice day!")

    except Exception as e:
        print(f"[system] Common run error:", e)


