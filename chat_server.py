import os
import tty
import tty
import time
import asyncio
from collections import deque
from asyncio import StreamReader, StreamWriter, Future
from tools.custom_readers import create_stdin_reader, read_line



class Server:
    def __init__(self):
        self._username_to_writer = {}                   # store all main users streamwriters here.
        self._online_global_chat = {}                   # show online users of global chat.   
        self._ban_db = {}                               # banned users.
        self._key = "secret_key"                        # for xor cryptography.

        self._control_tasks = {}                        # manage tasks by username.
        self._added_tasks = []                          # store all tasks.
        
                                                        # control servers lifetime for:
        self._shutdown_event_s_file_db = {}             # - sending file.
        self._shutdown_event_r_shell_db = {}            # - reversed shell.

        self._ports_db = [1, 2, 3, 4, 5, 6, 7, 8, 9]    # free server ports[8001-8009].
        
        # tmp for handling new sessions.
        # db store these active sessions.
        self._private_chat_tmp = {}         
        self._private_chat_db = {}      

        self._file_sending_tmp = {}         
        self._file_sending_db = {}            

        self._reverse_shell_tmp = {}       
        self._reverse_shell_db = {}

        



    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||Server section for file sending|||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    def _port_handling(self, command: str, port = None) -> int:
        try:
            if not len(self._ports_db):
                return 0
         
            if command == "dequeue":
                return self._ports_db.pop()
            
            elif command == "enqueue":
                self._ports_db.append(port)
                return 1  
       
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Port handling error, command: {command}, port: {port}, error: ", e)
            return 0


    async def _accept_file_name(self, reader: StreamReader, requester_name: str) -> None:
        try:
            if self._file_sending_db.get(requester_name, 0):
                while (file_name_size_bytes := await asyncio.wait_for(reader.readline(), 15)) != b'':
                    try:
                        file_name_size = int(file_name_size_bytes)

                        while (file_name := await asyncio.wait_for(reader.readexactly(file_name_size), 15)) != b'':
                            byte_array = file_name 
                            break
                                      
                        if file_name_size == len(byte_array):
                            self._file_sending_db[requester_name]["file_name_size"] = file_name_size_bytes
                            self._file_sending_db[requester_name]["file_name"] = file_name
                            break
                            
                        else:
                           raise Exception("Something wrong with length.")

                    except ValueError as e:
                        print(f"[system][{time.strftime('%X %x')} Something wrong with parsing file name length, requester name: {requester_name}, error:", e)
                        break

        except asyncio.exceptions.CancelledError:
            print(f"[system][{time.strftime('%X %x')}] Accept file name canceled, requester: {requester_name}")                 

        except asyncio.exceptions.TimeoutError:
            print(f"[system][{time.strftime('%X %x')}] Accept file name task cancelation, {requester_name} didn't receive a file name, requester: {requester_name}")
            self._file_sending_db[requester_name]["file_name"] = False

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Accept file name, requester: {requester_name}, error:", e)
            self._file_sending_db[requester_name]["file_name"] = False

            

    async def _accept_download(self, reader: StreamReader, writer: StreamWriter, requester_name: str) -> None:
        _time = 30
        file_name = None
        
        try:
            print(f"[system][{time.strftime('%X %x')}] Accept download activated, requester name: {requester_name}")
            
            accept_name_task = asyncio.create_task(self._accept_file_name(reader, requester_name))
            self._added_tasks.append(accept_name_task)
            self._control_tasks[requester_name]["accept_name"] = accept_name_task

            while self._file_sending_db.get(requester_name, 0) and self._file_sending_db[requester_name]["file_name"] or _time:
                if self._file_sending_db.get(requester_name, 0):
                    file_name = self._file_sending_db[requester_name]["file_name"]
                else:
                    raise Exception("While accepting file name, request was deleted from db.")
  
                if self._file_sending_db.get(requester_name, 0) and self._file_sending_db[requester_name]["file_name"] is False:
                    raise Exception("Something wrong with receiving file name")

                if file_name:
                    while (file_size_bytes := await asyncio.wait_for(reader.readline(), 15)) != b'':
                        try:     
                            file_size = int(file_size_bytes)
                            
                            while data := await asyncio.wait_for(reader.readexactly(file_size), 60):
                                buffer = data
                                break
                           
                            if len(buffer) > 2071611:
                                raise Exception("File size is more than 1gb")
                                           
                            if file_size == len(buffer):
                                self._file_sending_db[requester_name]["file_size"] = file_size_bytes
                                self._file_sending_db[requester_name]["buffer"] = buffer
                                self._file_sending_db[requester_name]["done"] = True

                                print(f"[system][{time.strftime('%X %x')}] File downloaded on server from: {requester_name}")
                                break
                        
                            else:
                               raise Exception("No file size or wrong type of file size received")
                            
                        except ValueError as e:
                            print(f"[system][{time.strftime('%X %x')} Something wrong with parsing file name length, requester name: {requester_name}, error:", e)

                         
                    writer.close()
                    await writer.wait_closed()
                    break
                
                else:
                    _time -=1
                    await asyncio.sleep(1)
                    writer.write(b'ping\n')
                    await writer.drain()
    
            if not _time:
                raise Exception(f"Time for waiting downloading from {requester_name} elapsed.")


        except ConnectionError as e:
            print(f"[system][{time.strftime('%X %x')}] No answer from other side while accepting download, requester name: {requester_name}, error:", e)
            await self._handle_exception_fsend_or_shell(requester_name, writer, "file")

        except asyncio.exceptions.CancelledError:
            print(f"[system][{time.strftime('%X %x')}] Accept download canceled, requester: {requester_name}")

        except asyncio.exceptions.TimeoutError:
            print(f"[system][{time.strftime('%X %x')}] No information from side that controls accept download, requester name: {requester_name}")
            await self._handle_exception_fsend_or_shell(requester_name, writer, "file")
            
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Accept file, requester name: {requester_name}, error: ", e)
            if not _time or not self._control_tasks[requester_name]["accept_name"].done():
                self._control_tasks[requester_name]["accept_name"].cancel()

            await self._handle_exception_fsend_or_shell(requester_name, writer, "file")

                
    async def _send_to_receiver(self, reader: StreamReader, writer: StreamWriter, requester_name: str) -> None:
        _time = 30
        
        try:
            print(f"[system][{time.strftime('%X %x')}] Send to receiver activated, requester name: {requester_name}")

            while _time:           
                if self._file_sending_db.get(requester_name, 0):
                    """ waiting from function acccept download confirmation that server downloaded
                        file and ready to send to other side"""
                    if self._file_sending_db[requester_name]["done"]:
                        file_name_size = self._file_sending_db[requester_name]["file_name_size"]
                        file_name = self._file_sending_db[requester_name]["file_name"]
                        file_size = self._file_sending_db[requester_name]["file_size"]
                        buffer = self._file_sending_db[requester_name]["buffer"]


                                                     # send:
                        writer.write(file_name_size) # - file name size.                               
                        writer.write(file_name)      # - name of the file.
                        await writer.drain()

                        writer.write(file_size)      # - file size.                    
                        writer.write(buffer)         # - send file.
                        await writer.drain() 
  
                        # shutdown server and close connection:
                        self._shutdown_event_s_file_db[requester_name].set()
                        await asyncio.sleep(1)
                        writer.close()
                        await writer.wait_closed()

                        # notify success file sending:
                        file_name_dec = self._xor_text(file_name.decode()).rstrip()
                        receiver = self._file_sending_db[requester_name]['receiver']
                  
                        message_req = f"[system] File: {file_name_dec} has been sent to {receiver}.\n"
                        await self._write_direct(self._username_to_writer[requester_name], message_req)
                        
                        message_rec = f"[system] File: {file_name_dec} has been sent to you.\n"
                        await self._write_direct(self._username_to_writer[self._file_sending_db[requester_name]["receiver"]], message_rec)

                        print(f"[system][{time.strftime('%X %x')}] File sent from requester: {requester_name} to receiver: {receiver}")
                        
                        if self._file_sending_db.get(requester_name, 0):
                            self._clear_data_connection(requester_name, "file")
                        break
            
                
                _time -= 1
                await asyncio.sleep(1)
   
                if not self._file_sending_db.get(requester_name, 0) or not _time:
                    if not _time:
                        raise Exception("Time for waiting to send the file elapsed.")
                    else:
                        raise Exception("Accept download already cleared the data.")


        except asyncio.exceptions.CancelledError as e:
            print(f"[system][{time.strftime('%X %x')}] Send to receiver canceled, requester name: {requester_name}")     
  
        except ConnectionError as e:
            print(f"[system][{time.strftime('%X %x')}] Send to receiver connection error, requester name: {requester_name}")   
            if self._control_tasks[requester_name].get("accept_name", 0):
                self._control_tasks[requester_name]["accept_name"].cancel()
                await asyncio.sleep(1)

            await self._handle_exception_fsend_or_shell(requester_name, writer, "file")
                
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Send to receiver, requester name: {requester_name}, error:", e)      
            if self._control_tasks[requester_name].get("accept_name", 0):
                self._control_tasks[requester_name]["accept_name"].cancel()
                await asyncio.sleep(1)

            if self._file_sending_db.get(requester_name, 0) and not self._file_sending_db[requester_name]["done"]:
                print(f"[system][{time.strftime('%X %x')}] No data in accept download, requester name: {requester_name}")

            await self._handle_exception_fsend_or_shell(requester_name, writer, "file")



        
    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||||||||Reversed Shell|||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    async def _ping_shell_connection(self, requester_name: str) -> None:      
        _time = 7
        
        try:
            dst_writer = self._reverse_shell_db[requester_name]["dst_writer"]
            src_writer = self._reverse_shell_db[requester_name]["src_writer"]
            
            while _time:
                if _time % 3 == 0:
                    dst_writer.write(b'[ping]\n')
                    await dst_writer.drain()

                    src_writer.write(b'[ping]\n')
                    await src_writer.drain()
                
                await asyncio.sleep(1)
                _time -= 1

                if not _time:
                    _time = 7
            
                
        except ConnectionError as e:          
            print(f"[system][{time.strftime('%X %x')}] Ping side if still connected connection error,  requester: {requester_name},  error:", e)

                
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Ping side if still connected, requester: {requester_name},  error:", e)

        finally:         
            if self._reverse_shell_db.get(requester_name, 0):
                await self._handle_exception_fsend_or_shell(requester_name, None, "shell")



    async def _receiver_control_requester_shell(self,  requester_name: str) -> None:
        _time = 30
        data = None
        src_writer = None
        dst_writer = None
        none_count = 0


        print(f"[system][{time.strftime('%X %x')}] Receiver control requester shell activated, requester name: {requester_name}")
  
        try:
            src_writer = self._reverse_shell_db[requester_name]["src_writer"]
     
            while _time:
                if not _time:
                    raise Exception("Time for waiting in receiver control requester shell elapsed")
                
                if self._reverse_shell_db.get(requester_name, 0) and \
                   self._reverse_shell_db[requester_name].get("dst_writer", 0) and \
                   self._reverse_shell_db[requester_name]["dst_writer"]:
                    _time = 0

                    ping_conn_task = asyncio.create_task(self._ping_shell_connection(requester_name))
                    self._added_tasks.append(ping_conn_task)
                    self._control_tasks[requester_name]["ping_conn"] = ping_conn_task
                                     
                    dst_writer = self._reverse_shell_db[requester_name]["dst_writer"]
                                                                                      # read:
                    src_reader = self._reverse_shell_db[requester_name]["src_reader"] # command from receiver
                    dst_reader = self._reverse_shell_db[requester_name]["dst_reader"] # to requester

                    
                    while (data := await asyncio.wait_for(src_reader.readline(), 333)) != b'':
                        if data == b"[ping]\n":
                            pass

                        else:
                            try: # read data from src_reader(receiver that sends commands to requesters shell)
                                len_data = int(data)
                                while (data := await asyncio.wait_for(src_reader.readexactly(len_data), 39)) != b'':
                                    byte_array = data
                                    break
                                
                                if len_data == len(byte_array):
                                    data = self._xor_text(byte_array.decode())
                                    await self._write_direct(dst_writer, data) # src_reader sends data to dst_writer
             
                                    if data == "exit\n":
                                        raise Exception("Exit command from src part, break task.")


                            except asyncio.exceptions.TimeoutError:
                                print(f"[system] Time elsaped, no information from src in reversed shell, requester name: {requester_name}")
                                data = None
                                                
                            except ValueError:
                                print(f"[system] Error while converting length of message from src_reader in receiver control requester shell, requester name: {requester_name}")
                                data = None
                                
                                 
                            except Exception as e:
                                print(f"[system] Common error from src_reader in receiver control requester shell, requester name: {requester_name}, error:", e)
                                data = None


                            if data is None:
                                break

             
                            try: # read output from dst reader's shell.
                                while (data := await asyncio.wait_for(dst_reader.readline(), 5)) != b'':
                                    len_data = int(data)
                                    
                                    while (data := await asyncio.wait_for(dst_reader.readexactly(len_data), 5)) != b'':
                                        byte_array = data
                                        break

                                    if len_data == len(byte_array):
                                        data = self._xor_text(byte_array.decode())
       
                                        if none_count and data != 'None.\n':
                                            none_count = 0
                                        if data == 'None.\n':
                                            none_count += 1
                                            if none_count == 3:
                                                message = "[system] More than 3 None from Shell - undefined behaviour, close connection."
                                                await self._write_direct(dst_writer, message)
                                                await self._write_direct(src_writer, message)       
                                                raise Exception(message)
                                            
                                        if data == b"[system]\n":
                                            message = "[system] You can use [system] tag."
                                            await self._write_direct(dst_writer, message)
                                   
                                        await self._write_direct(src_writer, data) # write output from dst shell to src.
                                        break
                                       

                                    else:
                                        raise Exception("Something wrong with length icontrol shell sending.")

                                    break


                            except asyncio.exceptions.TimeoutError as e:
                                print(f"[system] No information from side that provides shell, requester name: {requester_name}")
                                data = None           
                                    
                            except ValueError:
                                print(f"[system] Error while converting length of message from dst_reader in receiver control requester shell, requester name: {requester_name}")
                                data = None
                                      
                            except Exception as e:
                                print(f"[system] Error while reading output from dst readers shell, requester name: {requester_name},  error:", e)
                                data = None
        
                        if data == None or (data == 'None.\n' and none_count == 3):
                            break
                     
                elif not self._reverse_shell_db.get(requester_name, 0):
                    raise Exception("Something wrong, data from receiver control shell deleted")                       
                    break

                await asyncio.sleep(1)
                if _time:
                    _time -= 1

                
        except ConnectionError as e:
            print(f"[system][{time.strftime('%X %x')}] Receiver control requester Shell Connection error, requester: {requester_name}")                

        except asyncio.exceptions.CancelledError:
            print(f"[system][{time.strftime('%X %x')}] Receiver control requester shell canceled, requester: {requester_name}")  

        except asyncio.exceptions.TimeoutError:
            print(f"[system][{time.strftime('%X %x')}] No information from side that controls Shell, requester name: {requester_name}")                 

        except Exception as e: 
            print(f"[system][{time.strftime('%X %x')}] Control requester, requester name: {requester_name}, error:", e)

        finally:
            if self._reverse_shell_db.get(requester_name, 0):
                await self._handle_exception_fsend_or_shell(requester_name, None, "shell")

            if self._control_tasks[requester_name].get("ping_conn", 0):
                self._control_tasks[requester_name]["ping_conn"].cancel()
                await asyncio.sleep(1)
            
     
    async def _wait_receiver_shell_accept(self, requester_name: str) -> None:
        _time = 33

        print(f"[system][{time.strftime('%X %x')}] Wait receiver shell acccept activated, requester name: {requester_name}")

        try: 
            while _time:
                if self._reverse_shell_db.get(requester_name, 0) and \
                   self._reverse_shell_db[requester_name].get("src_reader", 0) and \
                   self._reverse_shell_db[requester_name]["src_reader"]:
                    print(f"[system][{time.strftime('%X %x')}] Receiver shell accepted, requester name: {requester_name}")
                    break

                elif not self._reverse_shell_db.get(requester_name, 0):
                    raise Exception("Something wrong, something already cleared data from shell accept")


                await asyncio.sleep(1)
                _time -= 1

                if not _time:
                    raise Exception("Time waiting receiver to accept shell elapsed")
                              

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Wait shell receiver, requester name: {requester_name}, error: ", e)
            
            if self._reverse_shell_db.get(requester_name, 0):
                await self._handle_exception_fsend_or_shell(requester_name, None, "shell")

                


    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||Common functions precisely for running server in contex of file sending or reversed||
        ||||||||||||||||||||||||||||||||||||||shell|||||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    async def _client_connected_file_or_shell(self, reader: StreamReader, writer: StreamWriter, requester_name: str, purpose: str) -> None:
        sync_protocol = None
        flag_error = False
        
        try:
            print(f"[system][{time.strftime('%X %x')}] Client connected, requester: {requester_name}, purpose: {purpose}")
            while (len_sync_protocol := await asyncio.wait_for(reader.readline(), 3)) != b'':
                try:
                    len_sync_protocol = int(len_sync_protocol)
                    
                    while (sync_protocol := await asyncio.wait_for(reader.readexactly(len_sync_protocol), 3)) != b'':
                        byte_array = sync_protocol
                        break
                    
                    if len_sync_protocol == len(byte_array):
                        sync_protocol = self._xor_text(byte_array.decode())
                            
                    else:
                       raise Exception(f"Something wrong with length.")
                         
                    sync_protocol = sync_protocol.rstrip()
                    print(f"[system][{time.strftime('%X %x')}] Protocol: {sync_protocol}")
                    
                    if sync_protocol == "[requester]": 
                        if purpose == "file":
                            self._file_sending_db[requester_name]["req_protocol"] = sync_protocol
                            await self._accept_download(reader, writer, requester_name)
                            
                        elif purpose == "shell":
                            self._reverse_shell_db[requester_name].update({"req_protocol": sync_protocol, "dst_reader": reader, "dst_writer": writer})
                            await self._wait_receiver_shell_accept(requester_name)

                    elif sync_protocol == "[receiver]":
                        if purpose == "file":
                            self._file_sending_db[requester_name]["rec_protocol"] = sync_protocol
                            await self._send_to_receiver(reader, writer, requester_name)

                        elif purpose == "shell":
                            self._reverse_shell_db[requester_name].update({"rec_protocol": sync_protocol, "src_reader": reader, "src_writer": writer})
      
                            rec_ctrl_req_shell_task = asyncio.create_task(self._receiver_control_requester_shell(requester_name))
                            self._added_tasks.append(rec_ctrl_req_shell_task)
                            self._control_tasks[requester_name]["rec_ctrl_req_shell"] = rec_ctrl_req_shell_task

                    break

                except ValueError as e:
                    print(f"[system][{time.strftime('%X %x')}] Error while parsing protocol length, requester name: {requester_name}, error:", e)
                    
                except Exception as e:
                    print(f"[system][{time.strftime('%X %x')}] Common error while parsing protocol length, requester name: {requester_name}, error:", e)
                    

                if sync_protocol is None or sync_protocol == b'':
                    raise Exception("Missing sync protocol")
                

        except asyncio.exceptions.CancelledError:
            print(f"[system][{time.strftime('%X %x')}] Client connected canceled, protocol: {sync_protocol}, requester: {requester_name}")
            flag_error = True

        except asyncio.exceptions.TimeoutError:
            print(f"[system][{time.strftime('%X %x')}] Client connected Timeout error,  protocol: {sync_protocol}, requester: {requester_name}")
            flag_error = True

        except Exception as e:           
            print(f"[system][{time.strftime('%X %x')}] Client connected, requester: {requester_name}, sync protocol: {sync_protocol}, error:", e)
            flag_error = True

        finally:
            if flag_error:       
                if purpose == "file":
                    if self._file_sending_db.get(requester_name, 0):
                        await self._handle_exception_fsend_or_shell(requester_name, writer, purpose)
     
                elif purpose == "shell":
                    if self._reverse_shell_db.get(requester_name, 0):
                        await self._handle_exception_fsend_or_shell(requester_name, None, purpose)



    async def _handle_exception_fsend_or_shell(self, requester_name: str,  writer: StreamWriter, purpose: str) -> None:
        try:
            if purpose == "file":                 
                if self._file_sending_db.get(requester_name, 0):
                
                    receiver = self._file_sending_db[requester_name]["receiver"]
                    message = f"[system][protocol_s_file][cancel]\n"
                    if self._username_to_writer.get(requester_name, 0):
                        await self._write_direct(self._username_to_writer[requester_name], message)

                    if self._username_to_writer.get(receiver, 0):
                        await self._write_direct(self._username_to_writer[receiver], message)

                    message_req = f"[system][server] Server closed file sending to user {receiver}.\n"
                    if self._username_to_writer.get(requester_name, 0):
                        await self._write_direct(self._username_to_writer[requester_name], message_req)

                    message_rec = f"[system][server] Server closed file transferring from user {requester_name}.\n"
                    if self._username_to_writer.get(receiver, 0):
                        await self._write_direct(self._username_to_writer[receiver], message_rec)
                
                    self._clear_data_connection(requester_name, "file")

                    if self._shutdown_event_s_file_db.get(requester_name, 0):
                        self._shutdown_event_s_file_db[requester_name].set()
                        await asyncio.sleep(1)
                    
                    
            elif purpose == "shell":
                if self._reverse_shell_db.get(requester_name, 0):
                    receiver = self._reverse_shell_db[requester_name]["receiver"]

                    if writer is None:
                        message_rq = f"[system][protocol_shell][rqcancel]\n"
                        if self._username_to_writer.get(requester_name, 0):
                            await self._write_direct(self._username_to_writer[requester_name], message_rq)
                                                   
                        message_rc = f"[system][protocol_shell][rccancel]\n"
                        if self._username_to_writer.get(receiver, 0):  
                            await self._write_direct(self._username_to_writer[receiver], message_rc)


                    message_req = f"[system][server] Server closed reverse shell with user {receiver}.\n"
                    if self._username_to_writer.get(requester_name, 0):
                        await self._write_direct(self._username_to_writer[requester_name], message_req)

                    message_rec = f"[system][server] Server closed reverse shell with user {requester_name}.\n"
                    if self._username_to_writer.get(receiver, 0):
                        await self._write_direct(self._username_to_writer[receiver], message_rec)

                    writer_rq = None
                    writer_rc = None
                    
                    if self._reverse_shell_db[requester_name].get("dst_writer", 0):          
                        writer_rq = self._reverse_shell_db[requester_name]["dst_writer"]
                        
                    if self._reverse_shell_db[requester_name].get("src_writer", 0):
                        writer_rc = self._reverse_shell_db[requester_name]["src_writer"]

                    self._clear_data_connection(requester_name, "shell")
                    count = 0

                    for writer in [writer_rq, writer_rc]:
                        try:
                            if writer != None:
                                count += 1
                                writer.close()
                                await writer.wait_closed()

                        except BrokenPipeError as e:
                            error_tag = "requester" if count == 1 else "receiver"
                            print(f"[system][{time.strftime('%X %x')}] shell handle exception closing writer: {error_tag}", e)

                    if self._shutdown_event_r_shell_db.get(requester_name, 0):
                        self._shutdown_event_r_shell_db[requester_name].set()
                        await asyncio.sleep(1)
                         
                            
            if writer != None:
                writer.close()
                await writer.wait_closed()
    
                      
        except Exception as e:
            print(f"[system] handle exception, purpose: {purpose}, requester: {requester_name}, error", e)


    async def _scan_if_user_connected_with_protocol(self, requester_name: str, purpose: str) -> None:
        _time = 5
        
        try:
            while _time:
                if purpose == "file":
                    if self._file_sending_db.get(requester_name, 0) and \
                       bool(self._file_sending_db[requester_name].get("req_protocol", 0)) and \
                            bool(self._file_sending_db[requester_name].get("rec_protocol", 0)):
                                 break # all good, both sides are connected.

                elif purpose == "shell":
                    if self._reverse_shell_db.get(requester_name, 0) and \
                       bool(self._reverse_shell_db[requester_name].get("req_protocol", 0)) and \
                            bool(self._reverse_shell_db[requester_name].get("rec_protocol", 0)):
                                 break # both sides are connected - all good.

                await asyncio.sleep(1)
                _time-=1


            if not _time:
                raise Exception("Something wrong with protocol, one or both sides are not connected")


        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Scan for protocols, purpose: {purpose}, requester: {requester_name} error:", e)
            if purpose == "file":
                if self._file_sending_db.get(requester_name, 0):
                    await self._handle_exception_fsend_or_shell(requester_name, None, purpose)

            elif purpose == "shell":
                if self._reverse_shell_db.get(requester_name, 0):
                    await self._handle_exception_fsend_or_shell(requester_name, None, purpose)



    async def _start_server_file_or_shell(self, requester_name: str, purpose: str)-> None:

        try:
            print(f"[system][{time.strftime('%X %x')}] [!] {purpose.title()} server launched, requester: {requester_name}")
            serve_forever_task = None
            actual_port = None
            run_server = None
            port = 8000
  
            # create shutdown event for server control:
            shutdown_event = asyncio.Event()
            shutdown_server_task = asyncio.create_task(shutdown_event.wait())
            
            if purpose == "file":
                self._shutdown_event_s_file_db[requester_name] = shutdown_event

            elif purpose == "shell":
                self._shutdown_event_r_shell_db[requester_name] = shutdown_event

            # starting server:
            if purpose == "file":
                if self._file_sending_db.get(requester_name, 0):
                    port += self._file_sending_db[requester_name]["port"]
                    scan_task = asyncio.create_task(self._scan_if_user_connected_with_protocol(requester_name, purpose))
                    run_server = await asyncio.start_server(lambda reader, writer: self._client_connected_file_or_shell(reader, writer, requester_name, purpose), "127.0.0.1", port)
                                 
            elif purpose == "shell":
                if self._reverse_shell_db.get(requester_name, 0):          
                    port += self._reverse_shell_db[requester_name]["port"]
                    scan_task = asyncio.create_task(self._scan_if_user_connected_with_protocol(requester_name, purpose))
                    run_server = await asyncio.start_server(lambda reader, writer: self._client_connected_file_or_shell(reader, writer, requester_name, purpose), "127.0.0.1", port)

            serve_forever_task = asyncio.create_task(run_server.serve_forever())


            async with run_server:
                done, pending = await asyncio.wait([serve_forever_task,  shutdown_server_task],
                                   return_when=asyncio.FIRST_COMPLETED)
                
                print(f"[system][{time.strftime('%X %x')}] Closing server, requester: {requester_name}, purpose:{purpose}")
                print(f"[system][{time.strftime('%X %x')}] Number of finished tasks: {len(done)}")
                print(f"[system][{time.strftime('%X %x')}] Number of waiting tasks: {len(pending)}")

                for done_task in done:
                    if done_task.exception() is None:
                        print(f"[system][{time.strftime('%X %x')}] Finished task in start server: {done_task}, requester name: {requester_name}, purpose: {purpose}")
                        
                    else:
                        print(f"[system][{time.strftime('%X %x')}] Exception task in start server: {done_task}, requester name: {requester_name}, purpose: {purpose}") 

                for pending_task in pending:
                    pending_task.cancel()
                    print(f"[system][{time.strftime('%X %x')}] Canceled task in start server: {pending_task}, requester name: {requester_name}, purpose: {purpose}") 

      
            print(f"[system][{time.strftime('%X %x')}] Server with requester name: {requester_name}, purpose: {purpose}, closed\n")

        except Exception as e:  
            print(f"[system][{time.strftime('%X %x')}] Start server, requester: {requester_name}, purpose: {purpose}, error", e)



    def _clear_data_connection(self, requester_name: str, purpose: str) -> None:
        try:
            if purpose == "file":
                self._port_handling("enqueue", self._file_sending_db[requester_name]["port"])
                del self._file_sending_db[requester_name]
    
            elif purpose == "shell":
                self._port_handling("enqueue", self._reverse_shell_db[requester_name]["port"])
                del self._reverse_shell_db[requester_name]

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Clear data connection, requester name:{requester_name}, error:", e)




        
    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        |||||||||||||||||||||||||||||||||Common tools|||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    def _xor_text(self, text: str) -> str:
        try:
            return ''.join(chr(ord(x) ^ ord(y)) for x, y in zip(text, self._key * (len(text) // len(self._key)) + self._key[:len(text) % len(self._key)]))
          
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Xor text: {text}, error:", e)


    
    def _extract_name(self, name: str) -> str:
        try:
            idx = 0
            checked_name = ""

            if name.startswith("[ban][del]"):
                idx = 10         
            elif name.startswith("[ban]"):
                idx = 5

            elif name.startswith("[p][ok]"):
                idx = 7        
            elif name.startswith("[p]"):
                idx = 3

            elif name.startswith("[send_file][ok]"):
                idx = 15
            elif name.startswith("[send_file]"):
                idx = 11

            elif name.startswith("[r_shell][ok]"):
                idx = 13

            elif name.startswith("[r_shell]"):
                idx = 9

            else: # f"{username}":
                idx = 0
                
            if name[idx] == "[" or not idx:
                start = idx if not idx else idx+1
                for el in name[start::]:
                    if el == "]" or not idx and el == ":":
                        checked_name+=el
                        break
                    
                    else:
                        checked_name+=el

                if checked_name[-1] not in ":]":
                   return 0 # error

                else:
                  checked_name = checked_name[:-1]

            return checked_name

        
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Common extract name, {name}, error:", e)
            return 0



    # write personal message no matter where is user is global or private:
    async def _write_direct(self, writer: StreamWriter, message: str) -> None:
        try:
            message = self._xor_text(message).encode()        
            len_msg = (str(len(message)) + '\n').encode()
            writer.write(len_msg)
            writer.write(message)
            await writer.drain()

        except ConnectionError as e:
            print(f"[system][{time.strftime('%X %x')}] Could not write direct to destination, error:", e)
            writer.close()
            await writer.wait_closed()

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Common error of writing direct, error:", e)
            writer.close()
            await writer.wait_closed()


    
    async def _wait_participant_to_accept(self, requester_name: str, purpose: str, flag_requester = None) -> None:
        """ action: file, private, shell """
        message_details = "receiving" if purpose == "file" else \
        ("session" if purpose == "private" else "control")
        message = None
        
        _time = 10
        
        try:
            while(_time):
                await asyncio.sleep(1)
       
                if purpose == "file":
                    await self._write_direct(self._file_sending_tmp[requester_name]["req_writer"], f"[system] {_time}s left.\n")
                    
                    # receiver accepted the connection:
                    if self._file_sending_tmp[requester_name]["token"]:

                        message = f"[system] Send file has been accepted. Wait for a while.\n"
                        await self._write_direct(self._file_sending_tmp[requester_name]["req_writer"], message)
                        await self._write_direct(self._file_sending_tmp[requester_name]["rec_writer"], message)
                        
                        # send protocol name with port number to requester and receiver:
                        message_req = f"[system][protocol_s_file][{self._file_sending_tmp[requester_name]['port']}][requester][{self._file_sending_tmp[requester_name]['receiver']}]\n"
                        message_rec = f"[system][protocol_s_file][{self._file_sending_tmp[requester_name]['port']}][receiver][{requester_name}]\n"
                        await self._write_direct(self._file_sending_tmp[requester_name]["req_writer"], message_req)
                        await self._write_direct(self._file_sending_tmp[requester_name]["rec_writer"], message_rec)
                        
                        # create task for file sending:
                        sending_file_task  = asyncio.create_task(self._start_server_file_or_shell(requester_name, purpose))

                        # add to main task:
                        self._added_tasks.append(sending_file_task)
                        self._control_tasks[requester_name]["file"] = sending_file_task

                        # transfer info about file action to active control, clear tmp file control:
                        self._file_sending_db[requester_name] = self._file_sending_tmp[requester_name].copy()
                        del self._file_sending_tmp[requester_name]
                        break


                elif purpose == "private":
                    await self._write_direct(self._private_chat_tmp[requester_name]["req_writer"], f"[system] {_time}s left.\n")   
                    
                    if self._private_chat_tmp[requester_name]["token"]:
                        if self._online_global_chat.get(requester_name, 0):                 # if in global chat then:
                            del self._online_global_chat[requester_name]                    # delete.
                            self._control_tasks[requester_name]["global_chat"].cancel()

                        elif self._control_tasks[requester_name].get("private_chat", 0):    # if user wants to switch from
                                                                                            # one private chat to another

                            self._control_tasks[requester_name]["private_chat"].cancel()
                            if flag_requester: # for receiver
                                await self._notify_user_left_private_chat(requester_name, flag_requester, True)
                                self._clear_data_private_request(requester_name, flag_requester)
                                await asyncio.sleep(1)
                            else:
                                dst_username = self._private_chat_db[requester_name]["receiver"]
                                await self._notify_user_left_private_chat(requester_name, dst_username)
                                self._clear_data_private_request(requester_name)
                                await asyncio.sleep(1)
                                
                            del self._control_tasks[requester_name]["private_chat"]

                        # transfer private session information to active control, clear tmp file control:
                        self._private_chat_db[requester_name] = self._private_chat_tmp[requester_name].copy()
                        del self._private_chat_tmp[requester_name]    

                        message = "[system] Private request has been accepted.\n"
                        await self._write_direct(self._private_chat_db[requester_name]["rec_writer"], message)
                        await self._write_direct(self._private_chat_db[requester_name]["req_writer"], message)

                        private_chat_task = asyncio.create_task(self._private_listen_for_messages(requester_name))  # create private task:
                        self._added_tasks.append(private_chat_task)                                                 # add to main:
                        self._control_tasks[requester_name]["private_chat"] = private_chat_task                     # control task
                        break


                elif purpose == "shell":
                    await self._write_direct(self._reverse_shell_tmp[requester_name]["req_writer"], f"[system] {_time}s left.\n")
                    
                    if self._reverse_shell_tmp[requester_name]["token"]:
                        # send protocol name with port number to requester and receiver:
                        message_req = f"[system][protocol_shell][{self._reverse_shell_tmp[requester_name]['port']}][requester][{self._reverse_shell_tmp[requester_name]['receiver']}]\n"
                        message_rec = f"[system][protocol_shell][{self._reverse_shell_tmp[requester_name]['port']}][receiver][{requester_name}]\n"
                        await self._write_direct(self._reverse_shell_tmp[requester_name]["req_writer"], message_req)
                        await self._write_direct(self._reverse_shell_tmp[requester_name]["rec_writer"], message_rec)

                        message = f"[system][server] Shell accepted.\n"
                        await self._write_direct(self._reverse_shell_tmp[requester_name]["req_writer"], message_req)
                        await self._write_direct(self._reverse_shell_tmp[requester_name]["rec_writer"], message_rec)

                        # create file task:
                        shell_task  = asyncio.create_task(self._start_server_file_or_shell(requester_name, purpose))

                        # gather for main:
                        self._added_tasks.append(shell_task)
                        self._control_tasks[requester_name]["shell"] = shell_task

                        # transfer shell session infomration to active control, clear tmp shell control:
                        self._reverse_shell_db[requester_name] = self._reverse_shell_tmp[requester_name].copy()
                        del self._reverse_shell_tmp[requester_name]
                        break

                _time-=1
            
                # if no connection - clear tmp, no sense to sending for active control - db:
                if not _time:
                    message = f"Time for waiting to accept: {purpose} {message_details} - elapsed"
                    raise Exception(message + ',' + f" requester name: {requester_name}")
    
        
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Common wait error, requester name: {requester_name}, error:", e)
            # message = "Time for waiting to accept: {purpose} {message_details} - elapsed"
            if purpose == "file":
                if self._file_sending_tmp.get(requester_name, 0):
                    if not _time:
                        message_req = f"[system] {message}.\n"
                        await self._write_direct(self._file_sending_tmp[requester_name]["req_writer"], message_req)                  
                    del self._file_sending_tmp[requester_name]
            
            elif purpose == "private":
                if self._private_chat_tmp.get(requester_name, 0):
                    if not _time:
                        message_req = f"[system] {message}.\n"
                        await self._write_direct(self._private_chat_tmp[requester_name]["req_writer"], message_req)
                    del self._private_chat_tmp[requester_name]

            elif purpose == "shell":
                if self._reverse_shell_tmp.get(requester_name, 0):
                    if not _time:
                        message_req = f"[system] {message}.\n" 
                        await self._write_direct(self._reverse_shell_tmp[requester_name]["req_writer"], message_req)
                    del self._reverse_shell_tmp[requester_name]
              
 



    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||Private chat section||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    async def _private_listen_for_messages(self, requester_name: str, flag_receiver = None, receiver_name = None) -> None:

        """ requester can be found easily in private session db by name, but for receiver was added
            flag_receiver which contains True.
        """
        _time = 5
        flag_cancel = None
        src_writer = None
        src_username = None
        
        try:
            while _time:
                if self._private_chat_db.get(requester_name, 0):                   
                    if receiver_name:
                        if self._private_chat_db[requester_name]["receiver"] == receiver_name:
                            break
                    else:
                        break
                    
                await asyncio.sleep(1)
                _time -= 1

            if not _time:
                raise Exception(f"Error with starting private listen messages, requester name: {requester_name} ")


            if flag_receiver:
                src_username = self._private_chat_db[requester_name]["receiver"]
                src_reader = self._private_chat_db[requester_name]["rec_reader"]
                src_writer = self._private_chat_db[requester_name]["rec_writer"]
                dst_writer = self._private_chat_db[requester_name]["req_writer"]
                dst_username = self._private_chat_db[requester_name]["requester"]
                
            elif not flag_receiver:
                src_username = self._private_chat_db[requester_name]["requester"]
                src_reader = self._private_chat_db[requester_name]["req_reader"]
                src_writer = self._private_chat_db[requester_name]["req_writer"]
                dst_writer = self._private_chat_db[requester_name]["rec_writer"]
                dst_username = self._private_chat_db[requester_name]["receiver"]
        
            print(f"[{time.strftime('%X %x')}] Username: {src_username} switched to private chat with username: {dst_username}")
            message = f"[system][server] You are now in private mode with {dst_username}, just start write messages or for moving back to global chat type: [global]\n"
            await self._write_direct(src_writer, message)
            
            while (data := await asyncio.wait_for(src_reader.readline(), 333)) != b'':
                try:
                    flag_cancel = False
                    len_msg = int(data)
                    
                    while (data := await asyncio.wait_for(src_reader.readexactly(len_msg), 9)) != b'':
                        byte_array = data
                        break

                    if len_msg == len(data):
                        data = self._xor_text(byte_array.decode())
                        print(f"[private][{time.strftime('%X %x')}][{src_username}]", data.rstrip())

                    else:
                        raise Exception(f"Something wrong with length of message from user: {src_username}")
    

                    if data.startswith("[system]"):
                        message = "[system] Your message can't be use  with the [system] tag in the beginning of the message.\n"
                        await self._write_direct(src_writer, message)


                    elif data.startswith("[ban][del]"):
                        sender = src_username
                        unban_user = self._extract_name(data)
                        
                        await self._unban_user(sender, unban_user)

                        
                    elif data.startswith("[ban]"):
                        sender = src_username
                        ban_user = self._extract_name(data)

                        await self._ban_user(sender, ban_user)


                    # go back to global chat:
                    elif data.startswith("[global]"):                                                                
                        # notify interlocutor that user left the chat:
                        if flag_receiver:
                            await self._notify_user_left_private_chat(src_username, dst_username, flag_receiver)      
                        else:
                            await self._notify_user_left_private_chat(src_username, dst_username)
                        
                        # add to global chat:
                        global_chat_task = asyncio.create_task(self._listen_for_messages(src_username, src_reader))
                        self._added_tasks.append(global_chat_task)
                        self._control_tasks[f"{src_username}"]["global_chat"] = global_chat_task                   
                        await asyncio.sleep(1)
                        
                        message = f"[system] Entered global.\n"
                        self._online_global_chat[src_username] = True
                        await self._write_direct(src_writer, message)
                        self._clear_data_private_request(src_username, requester_name) if flag_receiver else self._clear_data_private_request(src_username)
                        self._control_tasks[src_username]["private_chat"].cancel()
                        await asyncio.sleep(1)


                    elif data.startswith("[send_file][ok]"):
                        receiver_name = src_username
                        _requester_name = self._extract_name(data)

                        if not await self._standard_filter_message(receiver_name, _requester_name, "[send_file][ok]"):
                            pass

                        else:
                            self._file_sending_tmp[_requester_name]["token"] = "super secret token"
                            

                    elif data.startswith("[send_file]"):
                        _requester_name = src_username
                        receiver_name = self._extract_name(data)
                        
                        if not await self._standard_filter_message(_requester_name, receiver_name, "[send_file]"):
                            pass
                                
                        else:
                            port_number = None
                            if port_number := self._port_handling("dequeue"):
                                self._file_sending_tmp[_requester_name] = {"requester": _requester_name, "req_writer": self._username_to_writer[_requester_name],
                                                                         "receiver": receiver_name, "rec_writer": self._username_to_writer[receiver_name],
                                                                         "port": port_number, "file_name": None, "file_size": None, "buffer": b'',
                                                                         "token": "", "done": False}


                                message = f"[system][server] {requester_name} wants to send you a file. To accept:[send_file][ok][{_requester_name}] or do nothing.\n"
                                await self._write_direct(self._username_to_writer[receiver_name], message)

                                asyncio.create_task(self._wait_participant_to_accept(_requester_name, "file"))

                            else:
                                message = "[system][server] This operation can be done or server just overloaded. Try again later.\n"
                                await self._write_direct(self._username_to_writer[_requester_name], message)

                   # switch to other private chat:
                    elif data.startswith("[p][ok]"):
                        receiver_name = src_username
                        _requester_name = self._extract_name(data) # extract name from the message.
         
                        if not await self._standard_filter_message(receiver_name, _requester_name, "[p][ok]", "private"):
                            pass

                        else: # new private connection
                            if flag_receiver:
                                await self._notify_user_left_private_chat(src_username, dst_username, flag_receiver)      
                            else:
                                await self._notify_user_left_private_chat(src_username, dst_username)
                                

                            self._private_chat_tmp[_requester_name]["rec_reader"] = src_reader
                            self._private_chat_tmp[_requester_name]["rec_writer"] = self._username_to_writer[receiver_name]          
                            self._private_chat_tmp[_requester_name]["token"] = "secret_token"
                            
                            self._clear_data_private_request(src_username, requester_name) if flag_receiver else self._clear_data_private_request(src_username)


                            private_chat_task = asyncio.create_task(self._private_listen_for_messages(_requester_name, True, receiver_name))
                            self._added_tasks.append(private_chat_task)
                            tmp = self._control_tasks[src_username]["private_chat"]
                            self._control_tasks[src_username]["private_chat"] = private_chat_task                

                            flag_cancel = True
                            tmp.cancel()
                        
                     
                    elif data.startswith("[p]"):
                        _requester_name = src_username
                        receiver_name = self._extract_name(data)
                        
                        if not await self._standard_filter_message(_requester_name, receiver_name, "[p]", "private"):
                            pass

                        else:
                            # notify reciever about request.
                            message = f"[system] {requester_name} sent you request for private chat session: type [p][ok][{_requester_name}] or just ignore it.\n"
                            await self._write_direct(self._username_to_writer[receiver_name], message)


                            # notify requester about request acceptance time.
                            message = f"[system] Private request has been sent to {receiver_name}, 10s to accept invitation.\n"
                            await self._write_direct(self._username_to_writer[_requester_name], message)


                            # create private session request.  
                            self._private_chat_tmp[_requester_name] = {
                                "requester": _requester_name, "req_reader": src_reader, "req_writer": self._username_to_writer[_requester_name],
                                "receiver": receiver_name, "rec_reader": "", "rec_writer": "",
                                "token": ""
                                }


                            if flag_receiver:
                                asyncio.create_task(self._wait_participant_to_accept(_requester_name, "private", requester_name))
                            else:
                                asyncio.create_task(self._wait_participant_to_accept(_requester_name, "private"))


                    # Reverse shell section:
                    elif data.startswith("[r_shell][ok]"):    
                        receiver_name = src_username
                        _requester_name = self._extract_name(data)

                        if not await self._standard_filter_message(receiver_name, _requester_name, "[r_shell][ok]"):
                            pass

                        else:
                            self._reverse_shell_tmp[_requester_name]["token"] = "super secret token"

                            message = f"[system][server] Shell accepted {receiver_name}.\n"
                            await self._write_direct(self._username_to_writer[_requester_name], message)

         
                    elif data.startswith("[r_shell]"):
                        _requester_name = src_username
                        receiver_name = self._extract_name(data)

                        if not await self._standard_filter_message(_requester_name, receiver_name, "[r_shell]"):
                            pass

                        else:             
                            port_number = 0
                            if port_number := self._port_handling("dequeue"):
                                self._reverse_shell_tmp[_requester_name] = {"requester": _requester_name,
                                                                           "req_writer": self._username_to_writer[_requester_name],
                                                                           "req_reader": src_reader,
                                                                           "receiver": receiver_name,
                                                                           "rec_writer": self._username_to_writer[receiver_name],
                                                                           "rec_reader": "",
                                                                           "port": port_number,
                                                                           "token": ""}


                                message = f"[system] {requester_name} sent you reverse shell session: type [r_shell][ok][{_requester_name}] or forget it.\n"
                                await self._write_direct(self._username_to_writer[receiver_name], message)

                                # task for reverse shell will be created later in this function:
                                asyncio.create_task(self._wait_participant_to_accept(_requester_name, "shell"))

                            else:    
                                message = f"[system][protocol_shell][rqcancel]\n" 
                                await self._write_direct(self._username_to_writer[_requester_name], message)

                                message = "[system][server] Server is not available for such operation or just overloaded. Try again later.\n"
                                await self._write_direct(self._username_to_writer[_requester_name], message)
       
                    # Show online:
                    elif data.startswith("[online]"):
                        if flag_receiver:
                            if self._private_chat_db.get(requester_name, 0) and self._private_chat_db[requester_name]["receiver"] == src_username:
                                message = f"[system] 2 users online: {src_username}, {dst_username}.\n"
                                await self._write_direct(src_writer, message)
                            else:
                                message = f"[system] 1 user online: {src_username}.\n"
                                await self._write_direct(src_writer, message)
                                
                        # for requester:
                        else:
                            if receiver := self._private_chat_db[requester_name].get("receiver", 0):
                                message = f"[system] 2 users online: {src_username}, {dst_username}.\n"
                                await self._write_direct(src_writer, message)
                            else:
                                 message = f"[system] 1 user online: {src_username}.\n"
                                 await self._write_direct(src_writer, message)
     
                    else:
                        # write message in private:              
                        # for receiver:
                        if flag_receiver:
                            # when requester created new session, but previous receiver stays in the room.
                            if self._private_chat_db.get(requester_name, 0) and self._private_chat_db[requester_name]["receiver"] == src_username:
                                if not await self._msg_and_check_in_banned_list(src_username, dst_username):
                                    await self._private_write_messages(src_writer, dst_writer, src_username, f"[private] {src_username}: {data}")      
                            else:
                                message = "[system][system] Interlocutor has left the private chat. Use [global] tag to go back for global chat.\n"
                                await self._write_direct(src_writer, message)

                        # for requester:
                        else:
                            if self._private_chat_db.get(requester_name, 0) and self._private_chat_db[requester_name].get("receiver", 0):
                                if not await self._msg_and_check_in_banned_list(src_username, dst_username):
                                    await self._private_write_messages(src_writer, dst_writer, src_username, f"[private] {src_username}: {data}")
                            else:
                                message = "[system][system] Interlocutor has left private chat. Use [global] tag to go back for global chat.\n"
                                await self._write_direct(src_writer, message)
                                

                except ValueError as e:
                    print(f"[system][{time.strftime('%X %x')}] Error while converting length of message from user: {src_username}, error:", e) 
                
                except Exception as e:
                    print(f"[system][{time.strftime('%X %x')}] Common error while in private chat from user: {src_username}, error:", e)        

         
            # user has left the chat by force quite.
            if flag_receiver:
                await self._notify_user_left_private_chat(src_username, dst_username, flag_receiver)      
            else:
                await self._notify_user_left_private_chat(src_username, dst_username)

            print(f"[system][{time.strftime('%X %x')}] {src_username} has left the chat")
            await self._close_socket_clear_from_server_private(src_username, src_writer)

                              
        except asyncio.exceptions.TimeoutError:
            print(f"[system][{time.strftime('%X %x')}] {src_username} Private chat finished time, for user: {src_username}")
            message = "[system] If no online activity server disconects client in 333s.\n"
            if src_writer:
                await self._write_direct(src_writer, message)
            await self._close_socket_clear_from_server_private(src_username, src_writer)
         
        except asyncio.exceptions.CancelledError:
            flag_cleared = True
            print(f"[system][{time.strftime('%X %x')}] Private listen message canceled for user: {src_username}")
            

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Private listen message error for user: {src_username}, error:", e)
            message = f"[system][{time.strftime('%X %x')}] Error, disconnects from the server.\n"
            if src_writer:
                await self._write_direct(src_writer, message)
            await self._close_socket_clear_from_server_private(src_username, src_writer)

        finally:
            if not flag_cancel:
                self._clear_data_private_request(src_username, requester_name) if flag_receiver else self._clear_data_private_request(src_username)            
                    


    async def _close_socket_clear_from_server_private(self, username: str, src_writer: StreamWriter) -> None:
        try:
            del self._username_to_writer[username]                                
            src_writer.close()
            await src_writer.wait_closed()
    
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Close private socket error for user: {username}, error:", e)
            src_writer.close()
            await src_writer.wait_closed()
            

    
    def _clear_data_private_request(self, src_username, flag_requester = None) -> None:
        try:
            if flag_requester: # for receiver:
                if self._private_chat_db.get(flag_requester, 0) and self._private_chat_db[flag_requester]["receiver"] == src_username:
                    self._private_chat_db[flag_requester]["receiver"] = None
                    
                else: # no need, already deleted from requester => del self._private_chat_db[src_username]
                    pass
                   
            else: # for requester:
                if self._private_chat_db.get(src_username, 0):
                    del self._private_chat_db[src_username]
   
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Clear data private, username: {src_username}, error:", e)
            if self._control_tasks.get(src_username, 0) and self._control_tasks[src_username].get("private_chat", 0):
                self._control_tasks[src_username].cancel()



    async def _notify_user_left_private_chat(self, src_username: str, dst_username: str, flag_receiver = None) -> None:
        try:
            message = f"[system][server] {src_username} has left the private chat.\n"
            
            if flag_receiver: # for receiver:
                if self._private_chat_db.get(dst_username, 0) and self._private_chat_db[dst_username]["receiver"] == src_username:
                    await self._write_direct(self._username_to_writer[dst_username], message)
                     
            else: # for requester:
                if self._private_chat_db[src_username].get("receiver", 0):
                    await self._write_direct(self._username_to_writer[dst_username], message)

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Notify user left private chat, username: {src_username}, error:", e)



    async def _private_write_messages(self, src_writer: StreamWriter, dst_writer: StreamWriter,
                                           src_username: str, message: str) -> None:
        try: 
            private_space = [src_writer, dst_writer] # src should also see his message.
            xor_msg =  self._xor_text(message)
            message = xor_msg.encode()
            len_msg = (str(len(message)) + '\n').encode()
            
            for writer in private_space:
                try:
                    writer.write(len_msg)
                    writer.write(message)
                    await writer.drain()
                    
                except ConnectionError as e:
                    print(f"[system][{time.strftime('%X %x')}] {src_username} wasn't able to write private message to interlocutor, error: {e}")
                    message = "[system][server] Error, disconnects from the server.\n"
                    await self._write_direct(src_writer, message)
                    src_writer.close()
                    await src_writer.wait_closed()

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Private message write, username: {src_username}, error: {e}")





    """ ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||Chat server section|||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||Main||||||||||||||||||||||||||||||||||||||||||||||||
        ||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
    """

    
    async def _listen_for_messages(self, username: str, reader: StreamReader) -> None:   
        """ [tag]:
            send_file  - send a certain file, main chat remain.
            r_shell    - reverse shell, requester continues to receive/send messages in main 
                         chat and in the same time can see output from reverse shell.
                         requester continues to receive messages in main chat, but sends
                         messages via reverse shell connection to the requester.
            system     - notify user that only server can use this tag.     
            online     - show to user how much users currently online in global chat.             
            ban        - user ban a certain user. 
            p          - activate a private chat, main chat closed, switching to private chat.

            This function listens/handles users messages/commands.
        """
            
        try:
            print(f"[{time.strftime('%X %x')}] Username: {username} entered global chat")
            while (data := await asyncio.wait_for(reader.readline(), 333)) != b'':
                try:
                    len_msg = int(data)
                    
                    while (data := await asyncio.wait_for(reader.readexactly(len_msg), 9)) != b'':
                        byte_msg_array = data
                        break

                    if len_msg == len(data):
                        data = self._xor_text(byte_msg_array.decode())

                    else:
                        raise Exception(f"Something wrong with length of message from user: {username}")


                    print(f"[{time.strftime('%X %x')}][{username}]", data.rstrip()) # show message from the user.
                    
                     # notify user that his message can't start with the [system, server] tag:
                    if data.startswith("[system][server]"):
                        message = "[system][server] Your message can't be use  with the [system][server] tag in the beginning of the message.\n"
                        await self._write_direct(self._username_to_writer[username], message)


                    elif data.startswith("[system]"):
                        message = "[system][server] Your message can't be use  with the [system] tag in the beginning of the message.\n"
                        await self._write_direct(self._username_to_writer[username], message)


                    # show total users on global chat
                    elif data.startswith("[online]"):
                        message = "[system][server] Global online: len{self._online_global_chat}.\n"
                        await self._write_direct(self._username_to_writer[username], message)
                        

                    # delete from ban user.
                    elif data.startswith("[ban][del]"):
                        sender = username
                        unban_user = self._extract_name(data)

                        await self._unban_user(sender, unban_user)

                            
                    # ban certain user.
                    elif data.startswith("[ban]"):
                        sender = username
                        ban_user = self._extract_name(data)

                        await self._ban_user(sender, ban_user)


                    # Send file request section:
                
                    # barbara accepts file from george: 
                    # [send_file][[ok][barbara]
                    elif data.startswith("[send_file][ok]"):
                        receiver_name = username
                        requester_name = self._extract_name(data)

                        if not await self._standard_filter_message(receiver_name, requester_name, "[send_file][ok]"):
                            pass

                        else:
                            self._file_sending_tmp[requester_name]["token"] = "super secret token"


                    # george wants to send file to barbara:
                    # [send_file][barbara]
                    elif data.startswith("[send_file]"):
                        requester_name = username
                        receiver_name = self._extract_name(data)                
                        
                        if not await self._standard_filter_message(requester_name, receiver_name, "[send_file]"):
                            pass
                                
                        else:
                            
                            port_number = None
                            if port_number := self._port_handling("dequeue"):
                                self._file_sending_tmp[requester_name] = {"requester": requester_name, "req_writer": self._username_to_writer[requester_name],
                                                                         "receiver": receiver_name, "rec_writer": self._username_to_writer[receiver_name],
                                                                         "port": port_number, "file_name_size": None, "file_name": None, "file_size": None,
                                                                         "buffer": b'', "token": "", "done": False, "req_protocol": None, "rec_protocol": None}


                                message = f"[system][server] Waiting receiver to accept file download.\n"
                                await self._write_direct(self._username_to_writer[requester_name], message)

                                message = f"[system][server] {requester_name} wants to send you a file. To acept:[send_file][ok][{requester_name}] or do nothing.\n"
                                await self._write_direct(self._username_to_writer[receiver_name], message)

                                asyncio.create_task(self._wait_participant_to_accept(requester_name, "file"))

                            else:    
                                message = f"[system][protocol_s_file][cancel]\n" 
                                await self._write_direct(self._username_to_writer[requester_name], message)

                                message = "[system][server] Server is not available for such operation or just overloaded. Try again later.\n"
                                await self._write_direct(self._username_to_writer[requester_name], message)


                    # Private chat request section:
                                 
                    # when client accepts a private conference.
                    # receiver barbara gets invitation and sends ok to requester george.
                    # [p][ok][george]
                    elif data.startswith("[p][ok]"):
                        receiver_name = username
                        requester_name = self._extract_name(data) # extract name from the message.
                              
                        if not await self._standard_filter_message(receiver_name, requester_name, "[p][ok]"):
                            pass
                                             
                        else:
                            self._private_chat_tmp[requester_name]["rec_reader"] = reader
                            self._private_chat_tmp[requester_name]["rec_writer"] = self._username_to_writer[receiver_name]          
                            self._private_chat_tmp[requester_name]["token"] = "secret token"

                            private_chat_task = asyncio.create_task(self._private_listen_for_messages(requester_name, True, receiver_name))
                            self._added_tasks.append(private_chat_task)
                            self._control_tasks[receiver_name]["private_chat"] = private_chat_task
                            self._control_tasks[receiver_name]["global_chat"].cancel()
                            del self._online_global_chat[username]
                                                                   
                        

                    # when client sends invitation for a private session.                                       
                    # requester george sends invitation to receiver barbara.
                    # [p][barbara]
                    elif data.startswith("[p]"):
                        receiver_name = self._extract_name(data) # get username barbara from request:
                        requester_name = username

                        if not await self._standard_filter_message(requester_name, receiver_name, "[p]"):
                            pass
                                             
                        else:
                            # notify reciever about request.
                            message = f"[system][server] {requester_name} sent you request for private chat session: type [p][ok][{requester_name}] or just ignore it.\n"
                            await self._write_direct(self._username_to_writer[receiver_name], message)


                            # notify requester about request acceptance time.
                            message = f"[system][server] Private request has been sent to {receiver_name}, 10s to accept invitation.\n"
                            await self._write_direct(self._username_to_writer[requester_name], message)


                            # create private session request.  
                            self._private_chat_tmp[requester_name] = {
                                "requester": requester_name, "req_reader": reader, "req_writer": self._username_to_writer[requester_name],
                                "receiver": receiver_name, "rec_reader": None, "rec_writer": None,
                                "token": None
                                }

                            # task for private connection will be created later in this function:
                            asyncio.create_task(self._wait_participant_to_accept(requester_name, "private"))

                    
            
                    # Reverse shell section:              
                    elif data.startswith("[r_shell][ok]"):
                        
                        receiver_name = username
                        requester_name = self._extract_name(data)

                        if not await self._standard_filter_message(receiver_name, requester_name, "[r_shell][ok]"):
                            pass

                        else:
                            self._reverse_shell_tmp[requester_name]["token"] =  "super secret token"
                
         

                    elif data.startswith("[r_shell]"):
                        requester_name = username
                        receiver_name = self._extract_name(data)

                        if not await self._standard_filter_message(requester_name, receiver_name, "[r_shell]"):
                            pass

                        else:             
                            port_number = 0
                            if port_number := self._port_handling("dequeue"):
                                self._reverse_shell_tmp[requester_name] = {"requester": requester_name,
                                                                           "req_writer": self._username_to_writer[requester_name],
                                                                           "req_reader": reader,
                                                                           "receiver": receiver_name,
                                                                           "rec_writer": self._username_to_writer[receiver_name],
                                                                           "rec_reader": "",
                                                                           "port": port_number,
                                                                           "token": ""}

                                message = f"[system] {requester_name} sent you reverse shell session: type [r_shell][ok][{requester_name}] or forget it.\n"
                                #message = f"[system][server] {requester_name} send you shell.\n"
                                await self._write_direct(self._username_to_writer[receiver_name], message)

                                # task for reverse shell will be created later in this function:
                                asyncio.create_task(self._wait_participant_to_accept(requester_name, "shell"))

                            else:    
                                message = f"[system][protocol_shell][rqcancel]\n" 
                                await self._write_direct(self._username_to_writer[requester_name], message)

                                message = "[system][server] Server is not available for such operation or just overloaded. Try again later.\n"
                                await self._write_direct(self._username_to_writer[requester_name], message)

                            

                    # Send message to all online participants:
                    else:
                        await self._notify_all(f'{username}: {data}')


                except ValueError as e:
                    print(f"[system][{time.strftime('%X %x')}] Error while parsing length of message from user: {username}, error:", e) 

                
                except Exception as e:
                    print(f"[system][{time.strftime('%X %x')}] Common error while reading mesage in global: {username}, error:", e)                    

                 

            # user has left the chat:
            await self._notify_all(f"{username}: has left the chat.\n")
           

        except asyncio.exceptions.TimeoutError:
            print(f"[system][{time.strftime('%X %x')}] {username} Global chat has reached the time online duration.")
            message = "[system] If no activity on the server disconnects a client in 333s.\n"
            await self._write_direct(self._username_to_writer[username], message)
            await self._remove_user(username)

  
        except asyncio.exceptions.CancelledError:
            print(f"[system][{time.strftime('%X %x')}] {username} Global chat canceled.")

 
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Global listen message username: {username}, error: ", e)
            message = "[system] Common error, disconnects from the server.\n"
            writer = self._username_to_writer[username]
            await self._write_direct(writer, message)
            await self._remove_user(username)



    async def _ban_user(self, sender: str, ban_user: str) -> None:
        tag_banned = False
        try:
            if sender == ban_user:
                message = "[system][server] You can't ban yourself in the chat.\n"
                await self._write_direct(self._username_to_writer[sender], message)
                
            else:
                if self._ban_db.get(ban_user, 0):
                    if not self._ban_db[ban_user].get(sender, 0):
                        self._ban_db[ban_user].update({sender: True})
                        tag_banned = True
                    else:
                        message = f"[system][server] You already banned this user: {ban_user}.\n"
                        await self._write_direct(self._username_to_writer[sender], message)
                        
                else:
                    self._ban_db[ban_user] = {sender: True}
                    tag_banned = True

                if tag_banned:
                    message = f"[system][server] {ban_user} banned.\n"
                    await self._write_direct(self._username_to_writer[sender], message)

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Ban user, sender: {sender}, ban user: {ban_user}, error:", e)


 
    async def _unban_user(self, sender: str, unban_user: str) -> None:
        try:
            if sender == unban_user:
                message = "[system][server] You can't unban yourself in the chat.\n"
                await self._write_direct(self._username_to_writer[sender], message)
                
            else:
                if self._ban_db.get(unban_user, 0) and self._ban_db[unban_user].get(sender, 0):            
                    del self._ban_db[unban_user][sender]
                    message = f"[system][server] User {unban_user} has been deleted from ban.\n"
                    await self._write_direct(self._username_to_writer[sender], message)

                    # if empty - clear user from ban table:
                    if self._ban_db[unban_user] == {}:
                        del self._ban_db[unban_user]

                else:
                    message = "[system][server] No such user in the ban.\n"
                    await self._write_direct(self._username_to_writer[sender], message)

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Unban user, sender: {sender}, ban user: {unban_user}, error:", e)
                    

    
    async def _standard_filter_message(self, src_username: str, dst_username: str, purpose: str, scope = None) -> int:
        # scope = private chat else None for global.
        try:
            """ Common filters:
            """
            if not dst_username:
                if purpose == "[send_file]" or purpose == "[send_file][ok]":
                    message = f"[system][protocol_s_file][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)

                elif purpose == "[r_shell]" or purpose == "[r_shell][ok]":
                    message = f"[system][protocol_shell][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
          
                message = f"[system][server] Error in typing, template should be used strictly: {purpose}[name]\n"
                await self._write_direct(self._username_to_writer[src_username], message)
                return 0


            # avoid username sending request for himself.
            if src_username == dst_username:
                if purpose == "[send_file]" or purpose == "[send_file][ok]":
                    message = f"[system][protocol_s_file][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    
                elif purpose == "[r_shell]" or purpose == "[r_shell][ok]":
                    message = f"[system][protocol_shell][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)               
                    
                message = "[system][server] You can't send request to yourself.\n"
                await self._write_direct(self._username_to_writer[src_username], message)
                return 0


            # no such user online.
            if not self._username_to_writer.get(dst_username, 0):
                if purpose == "[send_file]" or purpose == "[send_file][ok]":
                    message = f"[system][protocol_s_file][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)

                elif purpose == "[r_shell]" or purpose == "[r_shell][ok]":
                    message = f"[system][protocol_shell][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    
                message = f"[system][server] {dst_username} it not online.\n"
                await self._write_direct(self._username_to_writer[src_username], message)
                return 0

        
            # check if banned:
            if await self._msg_and_check_in_banned_list(src_username, dst_username):
                if purpose == "[send_file]" or purpose == "[send_file][ok]":
                    message = f"[system][protocol_s_file][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    
                elif purpose == "[r_shell]" or purpose == "[r_shell][ok]":
                    message = f"[system][protocol_shell][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    
                return 0


            """ Sending file filters:
            """                   
            if purpose == "[send_file]":  
                if self._file_sending_tmp.get(src_username, 0):            
                    message = f"[system][server] You can send only one send file request.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0

                elif self._file_sending_tmp.get(dst_username, 0) and self._file_sending_tmp[dst_username]["receiver"] == src_username:
                    message = f"[system][server] You are already have send file request with this username: {dst_username}.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0

                else:
                    message_req = f"[system] Only one file sending task can be on the moment.\n"
                    if self._file_sending_db.get(src_username, 0) and self._file_sending_db[src_username]["receiver"] == dst_username:
                        await self._write_direct(self._username_to_writer[src_username], message_req)
                        return 0

                    elif self._file_sending_db.get(dst_username, 0) and self._file_sending_db[src_username]["receiver"] == src_username:
                        await self._write_direct(self._username_to_writer[src_username], message_req)
                        return 0
                
            elif purpose == "[send_file][ok]":
                if self._file_sending_tmp.get(dst_username, 0) and self._file_sending_tmp[dst_username]["receiver"] == src_username:
                    return 1
                else:
                    message = f"[system][protocol_s_file][cancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    message = "[system][server] There is no such request.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0


            """ Private chat filters:
            """
            if scope == "private": # if message came from private chat, user wants to switch in other private chat.
                message = f"[system][server] You are already have private chat with this username: {dst_username}.\n"
                if purpose == "[p]":    
                    if self._private_chat_db.get(src_username, 0) and self._private_chat_db[src_username]["receiver"] == dst_username:                   
                        await self._write_direct(self._username_to_writer[src_username], message)
                        return 0
                    
                    elif self._private_chat_db.get(dst_username, 0) and self._private_chat_db[dst_username]["receiver"] == src_username:
                        await self._write_direct(self._username_to_writer[src_username], message)
                        return 0      
                        
                    
                elif purpose == "[p][ok]":
                    if self._private_chat_db.get(dst_username, 0) and self._private_chat_db[dst_username]["receiver"] == src_username:
                        await self._write_direct(self._username_to_writer[src_username], message)
                        return 0

            
            # check for global and private: only one request can be.
            if purpose == "[p]":
                if self._private_chat_tmp.get(src_username, 0):           
                    message = f"[system][server] You can send only one private request.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0

                elif self._private_chat_tmp.get(dst_username, 0) and self._private_chat_tmp[dst_username]["receiver"] == src_username:
                    message = f"[system][server] You are already have private request with this username: {dst_username}.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0
                    

            elif purpose == "[p][ok]":
                if self._private_chat_tmp.get(dst_username, 0) and self._private_chat_tmp[dst_username]["receiver"] == src_username:
                    return 1

                else:   
                    message = "[system][server] There is no such request.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0


            """ Reverse shell
            """                
            if purpose == "[r_shell]":
                message_detail = "reverse shell" 
                if self._reverse_shell_tmp.get(src_username, 0) or self._reverse_shell_db.get(src_username, 0):                          
                    message = f"[system][server] You can have only one {message_detail} request.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0

                elif self._reverse_shell_db.get(src_username, 0) and self._reverse_shell_db[src_username]["receiver"] == dst_username or \
                     self._reverse_shell_db.get(dst_username, 0) and self._reverse_shell_db[dst_username]["receiver"] == src_username:
                    
                    message = f"[system][server] You already have an active {message_detail} with username: {dst_username}.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0


                else:
                    for username in self._reverse_shell_db:
                        if self._reverse_shell_db[username]["receiver"] == dst_username:
                            message = "[system][server] Server is not available for such operation.\n"
                            await self._write_direct(self._username_to_writer[src_username], message)
                            return 0


            elif purpose == "[r_shell][ok]":   
                if self._reverse_shell_tmp.get(dst_username, 0) and self._reverse_shell_tmp[dst_username]["receiver"] == src_username:
                    return 1
                else:
                    message = f"[system][protocol_shell][rccancel]\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    message_detail = "reverse shell" 
                    message = f"[system][server] There is no such {message_detail} request.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 0
 
            return 1

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Standard filter message, src username: {src_username}, dst username: {dst_username}, error: ", e)
            return 0



    async def _msg_and_check_in_banned_list(self, src_username: str, dst_username: str) -> int:
        try:
            if check := self._check_in_banned_list(src_username, dst_username):
                if check == 1:
                    message = f"[system][server] You are in username: {dst_username} banned list.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 1

                elif check == 2:
                    message = f"[system][server] Username: {dst_username} in your banned list.\n"
                    await self._write_direct(self._username_to_writer[src_username], message)
                    return 1
                
            return 0

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Msg and check banned, src username: {src_username}, dst username: {dst_username}, error: ", e)
            return 0


    
    def _check_in_banned_list(self, src_username: str, dst_username: str) -> int:
        try:
            ans = [0, 0]
            flag = 0
            
            # check if src_user in dst_user banned list.
            if self._ban_db.get(src_username, 0) and self._ban_db[src_username].get(dst_username, 0):
                ans[0] = 1
                flag+=1
                
            # src_user banned this dst_user.   
            elif self._ban_db.get(dst_username, 0) and self._ban_db[dst_username].get(src_username, 0):
                ans[1] = 1
                flag+=1

            if flag == 2: # src_user banned dst_user and dst_user banned src_user.   
                return 2

            if flag == 1:
                if ans[0] == 1: # src_user in dst_user banned list.
                    return 1
                
                if ans[1] == 1: # src_user banned dst_user.
                    return 2

            return 0

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Check banned, src username: {src_username}, dst username: {dst_username}, error: ", e)
            return 0
            


    async def _notify_all(self, message: str) -> None:
        src_username = None
        
        try:
            src_username = self._extract_name(message)
            inactive_users = []

            for username, writer in list(self._username_to_writer.items()):
                if self._check_in_banned_list(src_username, username):
                    continue

                else:            
                    try:
                        await self._write_direct(writer, message)
                       
                    except ConnectionError as e:
                        print(f"[system][{time.strftime('%X %x')}] Notify all could not write to client, username: {src_username}, error:", e)
                        inactive_users.append(username)

            [await self._remove_user(username) for username in inactive_users]

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Notify all, username: {src_username}, error:", e)



    async def _remove_user(self, username: str) -> None:
        writer = None
        try:
            if self._online_global_chat.get(username, 0):
                del self._online_global_chat[username]
            
            if self._username_to_writer.get(username, 0):
                writer = self._username_to_writer[username]
                del self._username_to_writer[username]
                
                try:
                    writer.close()
                    await writer.wait_closed()

                except Exception as e:
                    print(f"[system][{time.strftime('%X %x')}] Error closing client writer, username: {username}, ignoring, error:", e)

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Remove user, username: {username}, error:", e)
            

        
    def _check_name(self, name: str) -> int:
        length = 0
        num = None

        try:
            for el in name:
                if length > 10: # max name length
                    return 0

                num = ord(el)
                # [0-9]: 48 - 57, [A-Z]: 65 - 90, [a-z]: 97 - 122.
                if num < 48 or num > 57 and num < 65 or num > 90 and num < 97 or num > 122:
                    return 0
                
                length += 1

            if not length:
                return 0

            return 1

        except Exception as e:
            print(f"[system] Check name, name:{name}, error:", e)
            return 0



    async def _ping_users_to_check_if_they_online(self) -> None:
        writer = None
        username = None
        message = "[ping]\n"
        _time = 8
        
        try:
            while True:
                if _time % 3 == 0:
                    for username, writer in list(self._username_to_writer.items()):
                        try:
                            writer.write(message.encode())
                            await writer.drain()
                                
                        except ConnectionError as e:
                            print(f"[system][{time.strftime('%X %x')}] Ping user: {username} - disconnected", e)
                            writer.close()
                            await writer.wait_closed()
                            
                            del self._username_to_writer[username]
                            
                            for task_name, task in list(self._control_tasks[username].items()):
                                if not task.done():
                                    task.cancel()
                                    await asyncio.sleep(1)
                                                          
                await asyncio.sleep(1)                  
                _time -= 1

                if not _time:
                    _time = 8

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Ping users to check online, error:", e)

          
    # Main functions when chat server starting global chat:
    async def _client_connected(self, reader: StreamReader, writer: StreamWriter) -> None:
        username = None
        flag_error = False

        try:
            while (len_username := await asyncio.wait_for(reader.readline(), 33)) != b'':
                len_username = int(len_username)

                while (username := await asyncio.wait_for(reader.readexactly(len_username), 9)) != b'':
                    byte_array = username
                    break
                           
                if len_username == len(byte_array):
                    username = self._xor_text(byte_array.decode()).rstrip()
                    
                    if not self._check_name(username):
                        message = "[system][server] Name should contain only english letters and numbers, length 1-10 characters.\n"
                        await self._write_direct(writer, message)

                    elif self._username_to_writer.get(username, 0):
                        message = "[system] Such username is already exists.\n"
                        await self._write_direct(writer, message)        

                    else:
                        if self._add_user(username, reader, writer):
                            if await self._on_connect(username, writer):                          
                                asyncio.create_task(self._main(username, reader, writer))  # run main task gathering.
                            break       

                        else:
                            raise Exception("Unknown add user error")

        except ValueError:
            print(f"[system][{time.strftime('%X %x')}] Error in pasring username length")
            message = "[system][server] Error, disconnects from the server.\n"
            await self._write_direct(writer, message)
            await self._remove_user(username)
   

        except asyncio.exceptions.TimeoutError:
            print(f"[system][{time.strftime('%X %x')}] Client connected has reached the time online duration. asyncio.exceptions.TimeoutError")
            message = "[system][server] If no activityon - server disconnects a client in 333s.\n"
            await self._write_direct(writer, message)
            await self._remove_user(username)

                  
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Client connected error:", e)
            message = "[system][server] Error, disconnects from the server.\n"
            await self._write_direct(writer, message)
            await self._remove_user(username)


    
    def _add_user(self, username: str, reader: StreamReader, writer: StreamWriter) -> int:
        try:
            self._username_to_writer[username] = writer
            self._online_global_chat[username] = True
            return 1
        
        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Add user, username: {username},  error:", e)
            return 0



    async def _on_connect(self, username: str, writer: StreamWriter) -> int:
        try:
            message = f'Welcome! {len(self._online_global_chat)} user(s) are online!\n'
            await self._write_direct(writer, message)
            await self._notify_all(f"{username}: connected!\n")
            return 1

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] On connect error: {username}", e)
            message = "[system][server] Error, disconnects from the server.\n"
            await self._write_direct(writer, message)
            await self._remove_user(username)
            return 0


  
    # Gathering all tasks here:
    async def _main(self, username: str, reader: StreamReader, writer: StreamWriter) -> None:
        try:  
            self._added_tasks = []
            global_chat_task = asyncio.create_task(self._listen_for_messages(username, reader))
            self._added_tasks.append(global_chat_task)
            
            self._control_tasks[username]= {}
            self._control_tasks[username]["global_chat"] = global_chat_task
            
            print(f"[{time.strftime('%X %x')}] Username connected: {username}")

            await asyncio.gather(*self._added_tasks)       

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Main error: {username}, error:", e)
            message = "[system] Error, disconnects from the server.\n"
            await self._write_direct(writer, message)
            await self._remove_user(username)
            if self._control_tasks.get(username, 0) and self._control_tasks[username].get("global_chat", 0):
                self._control_tasks[username]["global_chat"].cancel()
                await asyncio.sleep(1)

  
  
    async def start_chat_server(self, host: str, port: int) -> None:
        try:
            server = await asyncio.start_server(self._client_connected, host, port)

            async with server:
                await server.serve_forever()

            

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Start chat server, host:{host}, port: {port}, error:", e)



    async def control_server(self, server) -> None:
        
        try:
            tty.setcbreak(0)
            os.system('clear')

            print("========================================")
            print("Hello, this is server terminal.\n")
            print("These commands provides common info:")
            print("1. online: online users")
            print("2. banned: banned users")
            print("3. ports: free ports\n")
            print("These commands show active sessions:")
            print("1. file: sending files")
            print("2. private: private")
            print("3. shell: reverse shell\n")
            print("For exit type: exit")
            print("=======================================")

            stdin_reader = await create_stdin_reader()

            while True:
                message = await read_line(stdin_reader)

                if message == "online":
                    print(f"[system][{time.strftime('%X %x')}] {message}")
                    print(f"[system] Total online {len(self._online_global_chat)}")
                    if len(self._online_global_chat):
                        print("---------------------------------------")
                        for name in self._online_global_chat:
                            print(name)
                        print("---------------------------------------")


                elif message == "banned":
                    print(f"[system][{time.strftime('%X %x')}] {message}")
                    if not len(self._ban_db):
                        print(f"[system] ban data is empty.")

                    else:
                        print("---------------------------------------")
                        for ban_user in self._ban_db:
                            print(f"[system] {ban_user} is banned in users db:")
                            [print(users, end=" ") for users in self._ban_db[ban_user]]
                            print()
                        print("---------------------------------------")


                elif message == "ports":
                    print(f"[system][{time.strftime('%X %x')}] {message}")
                    if not len(self._ports_db):
                        print(f"[system] Port are all busy.")

                    else:
                        print("---------------------------------------")
                        [print(ports, end=" ") for ports in self._ports_db]
                        print()
                        print("---------------------------------------")


                elif message == "file":
                    print(f"[system][{time.strftime('%X %x')}] {message}")
                    if not len(self._private_chat_db):
                        print("[system] No active sessions of file sending")

                    else:
                        print("---------------------------------------")
                        for requester in self._file_sending_db:
                            print(f"requester: {requester}, receiver : {self._file_sending_db[requester]['receiver']}")
                        print("---------------------------------------")

                            
                elif message == "private":
                    print(f"[system][{time.strftime('%X %x')}] {message}")
                    if not len(self._private_chat_db):
                        print("[system] No active private sessions")

                    else:
                        print("---------------------------------------")
                        for requester in self._private_chat_db:
                            print(f"requester: {requester}, receiver : {self._private_chat_db[requester]['receiver']}")
                        print("---------------------------------------")


                elif message == "shell":
                    print(f"[system][{time.strftime('%X %x')}] {message}")
                    if not len(self._reverse_shell_db):
                        print("[system] No active reverse shell sessions")

                    else:
                        print("---------------------------------------")
                        for requester in self._reverse_shell_db:
                            print(f"requester: {requester}, receiver : {self._reverse_shell_db[requester]['receiver']}")
                        print("---------------------------------------")


                elif message == "exit":
                    break

                else:
                    print(f"[system] {message} - unknown command")
 

        except Exception as e:
            print(f"[system][{time.strftime('%X %x')}] Control server error:", e)


    



if __name__ == "__main__":
    new_server = Server()
    
    async def main(server) -> None:   
        start_server_task = asyncio.create_task(server.start_chat_server('127.0.0.1', 8000))
        control_server_task = asyncio.create_task(server.control_server(server))
        ping_clients_task = asyncio.create_task(server._ping_users_to_check_if_they_online())

        await control_server_task



    try:
        asyncio.run(main(new_server))

    except Exception as e:
        print(f"[system][{time.strftime('%X %x')}] Run main error:", e)

    except KeyboardInterrupt as e:
        print("\nHave a wonderful day!")

