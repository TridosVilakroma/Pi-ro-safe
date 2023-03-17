import os,time,json,copy
import device_classes.mau as mau
import device_classes.exhaust as exhaust
import device_classes.light as light
import device_classes.drycontact as drycontact
import device_classes.gas_valve as gas_valve
import device_classes.micro_switch as micro_switch
import device_classes.heat_sensor as heat_sensor
import device_classes.switch_light as switch_light
import device_classes.switch_fans as switch_fans
from server import server
if os.name == 'nt':
    import RPi_test.GPIO as GPIO
else:
    import RPi.GPIO as GPIO

heat_sensor_timer=300
#there are only 25 GPIO pins available for input/output.
#the additional 15 are grounds, constant powers, and reserved for hats.
available_pins=[i for i in range(2,28)]

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

off=0
on=1
devices=[]
def get_devices():
    def load_devices():
        try:
            with open(rf"logs/devices/device_list.json","r") as read_file:
                data = json.load(read_file)
            return data
        except FileNotFoundError:
            print("logic.get_devices().load_devices(): FileNotFoundError; Creating file")
            with open(rf"logs/devices/device_list.json","w+") as read_file:
                data={}
                json.dump(data, read_file,indent=0)
            return load_devices()


    loaded_devices=load_devices()
    for d in loaded_devices:
        if d != "default" and not any(j for j in devices if j.name == d):
            i=eval(f"{loaded_devices[d]}(name=\"{d}\")")
            if i.pin in available_pins:
                available_pins.remove(i.pin)
                set_pin_mode(i)
            devices.append(i)

def set_pin_mode(device):
    if device.pin==0:
        print(f"logic.set_pin_mode(): {device}.pin == 0")
    else:
        if device.mode=="in":
            GPIO.setup(device.pin,GPIO.IN,pull_up_down = GPIO.PUD_DOWN)
        elif device.mode=="out":
            GPIO.setup(device.pin, GPIO.OUT,initial=GPIO.LOW)
        else:
            print(f"logic.set_pin_mode(): {device}.mode is not \"in\" or \"out\"")

def exfans_on():
    for i in (i for i in devices if isinstance(i,exhaust.Exhaust)):
        if i.pin!=0:
            GPIO.output(i.pin,on)
            i.on()

def exfans_off():
    for i in (i for i in devices if isinstance(i,exhaust.Exhaust)):
        GPIO.output(i.pin,off)
        i.off()

def maufans_on():
    for i in (i for i in devices if isinstance(i,mau.Mau)):
        if i.pin!=0:
            GPIO.output(i.pin,on)
            i.on()

def maufans_off():
    for i in (i for i in devices if isinstance(i,mau.Mau)):
        GPIO.output(i.pin,off)
        i.off()

def lights_on():
    for i in (i for i in devices if isinstance(i,light.Light)):
        if i.pin!=0:
            GPIO.output(i.pin,on)
            i.on()

def lights_off():
    for i in (i for i in devices if isinstance(i,light.Light)):
        GPIO.output(i.pin,off)
        i.off()

def dry_on():
    for i in (i for i in devices if isinstance(i,drycontact.DryContact)):
        if i.pin!=0:
            GPIO.output(i.pin,on)
            i.on()

def dry_off():
    for i in (i for i in devices if isinstance(i,drycontact.DryContact)):
        GPIO.output(i.pin,off)
        i.off()

def gv_on():
    for i in (i for i in devices if isinstance(i,gas_valve.GasValve)):
        if i.pin!=0 and i.latched:
            GPIO.output(i.pin,on)
            i.on()

def gv_off():
    for i in (i for i in devices if isinstance(i,gas_valve.GasValve)):
        GPIO.output(i.pin,off)
        i.off()

def gv_reset_all(*args):
    for i in (i for i in devices if isinstance(i,gas_valve.GasValve)):
        i.latched=True

def save_devices(*args):
    for i in devices:
        i.write()

def update_devices(*args):
    for i in devices:
        i.update()

def pin_off(pin):
    func = GPIO.gpio_function(pin)
    if func==GPIO.OUT:
        GPIO.output(pin,off)

dry_contact=12
lights_pin=7
if os.name == 'nt':
    def heat_sensor_active():
        for i in (i for i in devices if isinstance(i,heat_sensor.HeatSensor)):
            if GPIO.input(i.pin,'h'):
                return True
        return False
    def micro_switch_active():
        for i in (i for i in devices if isinstance(i,micro_switch.MicroSwitch)):
            if GPIO.input(i.pin,'m'):
                return True
        return False
    def fan_switch_on():
        for i in (i for i in devices if isinstance(i,switch_fans.SwitchFans)):
            if GPIO.input(i.pin,'f'):
                return True
        return False
    def light_switch_on():
        for i in (i for i in devices if isinstance(i,switch_light.SwitchLight)):
            if GPIO.input(i.pin,'l'):
                return True
        return False
if os.name == 'posix':
    def heat_sensor_active():
        for i in (i for i in devices if isinstance(i,heat_sensor.HeatSensor)):
            if GPIO.input(i.pin):
                return True
        return False
    def micro_switch_active():
        for i in (i for i in devices if isinstance(i,micro_switch.MicroSwitch)):
            if not GPIO.input(i.pin):
                return True
        return False
    def fan_switch_on():
        for i in (i for i in devices if isinstance(i,switch_fans.SwitchFans)):
            if GPIO.input(i.pin):
                return True
        return False
    def light_switch_on():
        for i in (i for i in devices if isinstance(i,switch_light.SwitchLight)):
            if GPIO.input(i.pin):
                return True
        return False
def clean_exit():
    all_pins=[i for i in range(2,28)]
    GPIO.setup(all_pins, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)

def clean_list(list,element):
    while True:
        try:
            list.remove(element)
        except ValueError:
            break

class Logic():
    def __init__(self) -> None:
        self.last_server_state={}
        self.aux_state=[]
        self.state='Normal'
        self.running=False
        self.shut_off=False
        self.fired=False
        self.sensor_target=time.time()

        '''two dictionaries are used to share data between two threads.
        moli: main out logic in, is written too in main and read in logic.
        milo: main in logic out, is written too in logic and read in main.
        '''
        self.troubles={
            'heat_override':0,
            'short_duration':0,
            'gv_trip':0
        }

        self.moli={
            'exhaust':off,
            'mau':off,
            'lights':off,
            'dry_contact':off,
            'maint_override':off,
            'maint_override_light':off
        }
        self.milo={
            'exhaust':off,
            'mau':off,
            'lights':off,
            'heat_sensor':off,
            'dry_contact':off,
            'micro_switch':off,
            'troubles':self.troubles
        }

    def normal(self):
        if micro_switch_active():
            print('micro_switch')
            self.state='Fire'
            self.milo['micro_switch']=on
        elif self.moli['maint_override']==1:
            dry_on()
            gv_on()
            exfans_off()
            maufans_off()
            if self.moli['maint_override_light']==1:
                lights_on()
            elif self.moli['maint_override_light']==0:
                lights_off()
        else:

            dry_on()
            gv_on()

            if self.moli['exhaust']==on or fan_switch_on():
                exfans_on()
                self.milo['exhaust']=on
            elif self.moli['exhaust']==off or not fan_switch_on():
                exfans_off()
                self.milo['exhaust']=off
            if self.moli['mau']==on or fan_switch_on():
                maufans_on()
                self.milo['mau']=on
            elif self.moli['mau']==off or not fan_switch_on():
                maufans_off()
                self.milo['mau']=off
            if heat_sensor_active():
                self.milo['heat_sensor']=on
                self.heat_trip()
            else:
                self.milo['heat_sensor']=off
            if self.moli['lights']==on or light_switch_on():
                lights_on()
                self.milo['lights']=on
            elif self.moli['lights']==off or not light_switch_on():
                lights_off()
                self.milo['lights']=off
    def heat_trip(self):
        self.sensor_target=time.time()+heat_sensor_timer
        self.aux_state.append('heat_sensor')
        print('heat trip')

    def heat_sensor(self):
            if self.sensor_target>=time.time():
                exfans_on()
                maufans_on()
                self.milo['exhaust']=on
                self.milo['mau']=on
                self.milo['heat_sensor']=on
                print('heat timer active')
            else:
                if self.moli['exhaust']==off and self.moli['mau']==off:
                    exfans_off()
                    maufans_off()
                self.milo['exhaust']=off
                self.milo['mau']=off
                self.milo['heat_sensor']=off
                clean_list(self.aux_state,'heat_sensor')


    def trouble(self):
    #heat sensor active
        if heat_sensor_active() and not self.moli['exhaust']==1:
            self.milo['troubles']['heat_override']=1
        else:
            self.milo['troubles']['heat_override']=0
    #heat timer
        if heat_sensor_timer==10:
            self.milo['troubles']['short_duration']=1
        else:
            self.milo['troubles']['short_duration']=0
    #gas valve unlatched
        if any(i for i in devices if isinstance(i,gas_valve.GasValve) and i.pin!=0 and not i.latched):
            self.milo['troubles']['gv_trip']=1
        else:
            self.milo['troubles']['gv_trip']=0

    def fire(self):
        if not self.fired:
            exfans_on()
            maufans_off()
            lights_off()
            dry_off()
            gv_off()
            self.fired = True
        if not micro_switch_active():
            self.fired = False
            self.state='Normal'
            self.milo['micro_switch']=off

    def server_update(self,*args):
        if self.last_server_state==self.milo:
            return
        try:
            server.toggleDevice(server.devices.exhaust , self.milo['exhaust'])
        except Exception as e:
            print(f'logic.py server_update(): {e}')
        try:
            server.toggleDevice(server.devices.lights, self.milo['lights'])
        except Exception as e:
            print(f'logic.py server_update(): {e}')
        self.last_server_state=copy.deepcopy(self.milo)

    def auxillary(self):
        self.trouble()
        if 'heat_sensor' in self.aux_state and not self.fired:
            self.heat_sensor()

    def state_manager(self):
        if self.state=='Fire':
            self.fire()
            print("fired state")
        elif self.state=='Normal':
            self.normal()
            print("normal state")

    def update(self):
        self.state_manager()
        self.auxillary()
        self.server_update()
get_devices()
fs=Logic()
def logic():
    while True:
        fs.update()
        time.sleep(.5)

if __name__=='__main__':
    try:
        logic()
    finally:
        clean_exit()