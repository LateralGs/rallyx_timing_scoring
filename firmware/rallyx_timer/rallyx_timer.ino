#include <TimerOne.h>
#include <Wire.h>
#include <EEPROM.h>
#include <string.h>
#include <strings.h>
#include <stdlib.h>

#define PIN_LED 13 // internal debug led
#define PIN_SQW 22
#define PIN_SCL 19
#define PIN_SDA 18
#define PIN_TS  0
#define PIN_TF  1
#define PIN_MTS 2
#define PIN_MTF 3

// all time is in milliseconds
#define DEFAULT_DEBOUNCE 10
#define DEFAULT_DEADTIME 10000

// increment this any time the rom format is changed or needs to be cleared
#define EEPROM_VERSION 0

typedef enum {
  ROM_OFFSET_VERSION=0,
  ROM_OFFSET_DEBOUNCE,
  ROM_OFFSET_DEADTIME,
  ROM_OFFSET_START
} rom_offset_t;

typedef enum {
  SOURCE_START = 0,
  SOURCE_FINISH,
  SOURCE_MANUAL_START,
  SOURCE_MANUAL_FINISH
} time_source_t;

typedef struct 
{
  uint32_t  pin;
  bool      active;
  uint32_t  debounce_count;
  uint32_t  deadtime_count;
  uint32_t  time;
} trigger_state_t;

typedef struct
{
  uint32_t time;
  time_source_t source;
} time_event_t;

volatile uint32_t debounce = DEFAULT_DEBOUNCE; // max number of debounce cycles
volatile uint32_t deadtime = DEFAULT_DEADTIME; // deadtime before next trigger

volatile uint32_t ms_time = 0; // master millisecond time

volatile uint32_t trigger_count = 0;

volatile trigger_state_t start_trigger = {PIN_TS, false, 0, 0};
volatile trigger_state_t finish_trigger = {PIN_TF, false, 0, 0};
volatile trigger_state_t manual_start_trigger = {PIN_MTS, false, 0, 0};
volatile trigger_state_t manual_finish_trigger = {PIN_MTF, false, 0, 0};

bool update_trigger( volatile trigger_state_t * trigger )
{
  // triggers are active low
  // debounce_count follows pin state
  if( digitalRead(trigger->pin) )
  {
    trigger->debounce_count = trigger->debounce_count < debounce ? trigger->debounce_count + 1 : debounce;
  }
  else
  {
    trigger->debounce_count = trigger->debounce_count > 0 ? trigger->debounce_count - 1 : 0;
  }

  trigger->deadtime_count = trigger->deadtime_count > 0 ? trigger->deadtime_count - 1 : 0;

  if( trigger->active == false && trigger->debounce_count == 0 )
  {
    // falling debounced edge detected
    trigger->active = true;

    if( trigger->deadtime_count == 0 )
    {
      trigger->time = ms_time;
      trigger->deadtime_count = deadtime;
    }
    return true;
  }
  else if( trigger->active == true && trigger->debounce_count >= debounce )
  {
    // rising debounced edge detected
    trigger->active = false;
    return false;
  }
  else
  {
    // no change
    return false;
  }
}

void timer_tick(void)
{
  ms_time++;

  update_trigger(&start_trigger);
  update_trigger(&finish_trigger);
  update_trigger(&manual_start_trigger);
  update_trigger(&manual_finish_trigger);
}

uint32_t eeprom_read(uint32_t offset)
{
  uint32_t value;
  uint32_t addr = offset * 4;

  value = EEPROM.read(addr+0);
  value |= EEPROM.read(addr+1) << 8;
  value |= EEPROM.read(addr+2) << 16;
  value |= EEPROM.read(addr+3) << 24;

  return value;
}

void eeprom_write(uint32_t offset, uint32_t value)
{
  uint32_t addr = offset * 4;

  EEPROM.write(addr+0, value & 0xff);
  EEPROM.write(addr+1, (value >> 8) & 0xff);
  EEPROM.write(addr+2, (value >> 16) & 0xff);
  EEPROM.write(addr+3, (value >> 24) & 0xff);
}

void format_eeprom(void)
{
  eeprom_write(ROM_OFFSET_VERSION, EEPROM_VERSION);
  eeprom_write(ROM_OFFSET_DEBOUNCE, debounce);
  eeprom_write(ROM_OFFSET_DEADTIME, deadtime);
  eeprom_write(ROM_OFFSET_START, 0xff);
}

void print_time(uint32_t time)
{
  uint32_t ms = time % 1000;
  uint32_t s = (time / 1000) % 60;
  uint32_t m = (time / 60000) % 60;
  uint32_t h = time / 3600000;

  if( h < 10 )
    Serial.write('0');
  Serial.print(h);
  Serial.write(':');
  if( m < 10 )
    Serial.write('0');
  Serial.print(m);
  Serial.write(':');
  if( s < 10 )
    Serial.write('0');
  Serial.print(s);
  Serial.write('.');
  if( ms < 100 )
    Serial.write('0');
  if( ms < 10 )
    Serial.write('0');
  Serial.print(ms);
}

void setup(void)
{
  for( uint32_t pin = 0; pin < 34; pin++ )
  {
    switch(pin)
    {
      case PIN_LED:
        pinMode(pin, OUTPUT);
        break;
      default:
        pinMode(pin, INPUT_PULLUP);
        break;
    }
  }

  Serial.begin(0);

  if( eeprom_read(ROM_OFFSET_VERSION) != EEPROM_VERSION )
  {
    format_eeprom();
  }
  else // load eeprom settings
  {
    debounce = eeprom_read(ROM_OFFSET_DEBOUNCE);
    deadtime = eeprom_read(ROM_OFFSET_DEADTIME);
  }

  Timer1.initialize(1000);
  Timer1.attachInterrupt(timer_tick);
  Timer1.start();
}

void command_process(char * cmd, uint32_t value, bool val_ok )
{
  if( strcasecmp(cmd, "ping") == 0 )
  {
    Serial.print("P ");
    Serial.println(value);
  }
  else if( strcasecmp(cmd, "recall") == 0 )
  {
    //Serial.println("R M1 01:23:45.678 123345 123");
    Serial.println("E not implemented");
  }
  else if( strcasecmp(cmd, "clear") == 0 )
  {
    //Serial.println("C");
    Serial.println("E not implemented");
  }
  else if( strcasecmp(cmd, "debounce") == 0 )
  {
    if( val_ok )
    {
      debounce = value;
      eeprom_write(ROM_OFFSET_DEBOUNCE, debounce);
    }
    Serial.print("B ");
    Serial.println(debounce);
  }
  else if( strcasecmp(cmd, "deadtime") == 0 )
  {
    if( val_ok )
    {
      deadtime = value;
      eeprom_write(ROM_OFFSET_DEADTIME, deadtime);
    }
    Serial.print("D ");
    Serial.println(deadtime);
  }
  else
  {
    Serial.println("E bad command");
    Serial.print("E ");
    Serial.println(cmd);
  }
}

void command_update(void)
{
  static char buffer[256];
  static uint32_t count = 0;
  char c;
  char *cmd;
  char *param;
  char *endptr;
  uint32_t value;

  while( Serial.available() )
  {
    c = Serial.read();
    switch( c )
    {
      case '\r':
      case '\n':
        if( count > 0 )
        {
          // parse command
          // format: <cmd> <value>
          cmd = strtok(buffer, " ");
          param = strtok(NULL, " ");
          value = param != NULL ? strtoul(param, &endptr, 0) : 0;

          command_process(cmd, value, (param != NULL) && (*endptr == 0));

          // reset buffer
          count = 0;
          buffer[count] = 0;
        }
        break;
      case 8:  // delete/backspace
        if( count > 0 )
        {
          count--;
          buffer[count] = 0;
        }
        break;
      case '\t':
        // convert tabs to single space
        c = ' ';
        // fall through to ' '
      case ' ':
        // filter out leading and multiple whitespace
        if( count == 0 || buffer[count-1] == ' ')
        {
          break;
        }
        // fall through to default
      default:
        if( c >= 32 && count < (sizeof(buffer) - 1) )
        {
          buffer[count] = c;
          count++;
          buffer[count] = 0;
        }
        break;
    }
  }
}

void loop_wait(void)
{
  static uint32_t prev_time = 0;
  while( prev_time == ms_time );
  prev_time = ms_time;
}

void loop(void)
{
  digitalWrite(PIN_LED, HIGH);

  if( start_trigger.time )
  {
    Serial.print("T 1 ");
    print_time(start_trigger.time);
    Serial.write(' ');
    Serial.print(start_trigger.time);
    Serial.write(' ');
    Serial.println(trigger_count++);
    start_trigger.time = 0;
  }

  if( finish_trigger.time )
  {
    Serial.print("T 2 ");
    print_time(finish_trigger.time);
    Serial.write(' ');
    Serial.print(finish_trigger.time);
    Serial.write(' ');
    Serial.println(trigger_count++);
    finish_trigger.time = 0;
  }

  if( manual_start_trigger.time )
  {
    Serial.print("T M1 ");
    print_time(manual_start_trigger.time);
    Serial.write(' ');
    Serial.print(manual_start_trigger.time);
    Serial.write(' ');
    Serial.println(trigger_count++);
    manual_start_trigger.time = 0;
  }

  if( manual_finish_trigger.time )
  {
    Serial.print("T M2 ");
    print_time(manual_finish_trigger.time);
    Serial.write(' ');
    Serial.print(manual_finish_trigger.time);
    Serial.write(' ');
    Serial.println(trigger_count++);
    manual_finish_trigger.time = 0;
  }

  command_update();

  digitalWrite(PIN_LED, LOW);

  loop_wait();
}

