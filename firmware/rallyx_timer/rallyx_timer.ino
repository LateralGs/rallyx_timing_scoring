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

#define EVENT_MAX 2048

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
  SOURCE_MANUAL_FINISH,
} source_t;

typedef struct 
{
  uint32_t  pin;
  bool      active;
  uint32_t  debounce_count;
  uint32_t  deadtime_count;
  uint64_t  time;
  source_t  source;
} trigger_state_t;

typedef struct
{
  uint64_t time;
  source_t source;
} event_t;

volatile uint32_t debounce = DEFAULT_DEBOUNCE; // max number of debounce cycles
volatile uint32_t deadtime = DEFAULT_DEADTIME; // deadtime before next trigger

volatile uint64_t ms_time = 0; // master millisecond time

volatile uint32_t event_count = 0;
volatile event_t events[EVENT_MAX];

#define INIT_TRIGGER(pin, source) {pin, false, 0, 0, 0, source}

volatile trigger_state_t start_trigger = INIT_TRIGGER(PIN_TS, SOURCE_START);
volatile trigger_state_t finish_trigger = INIT_TRIGGER(PIN_TF, SOURCE_FINISH);
volatile trigger_state_t manual_start_trigger = INIT_TRIGGER(PIN_MTS, SOURCE_MANUAL_START);
volatile trigger_state_t manual_finish_trigger = INIT_TRIGGER(PIN_MTF, SOURCE_MANUAL_FINISH);

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
      events[event_count % EVENT_MAX].time = ms_time;
      events[event_count % EVENT_MAX].source = trigger->source;
      event_count++;
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

void print_uint64(uint64_t value)
{
  char buf[32];
  int i = 0;

  if( value == 0 )
  {
    Serial.print('0');
  }

  while( value > 0 )
  {
    buf[i++] = '0' + (value % 10);
    value /= 10;
  }
  while( i > 0 )
  {
    Serial.print(buf[i-1]);
    i--;
  }
}

void print_event(uint32_t index)
{
  switch(events[index].source)
  {
    case SOURCE_START:
      Serial.print("1 ");
      break;
    case SOURCE_FINISH:
      Serial.print("2 ");
      break;
    case SOURCE_MANUAL_START:
      Serial.print("M1 ");
      break;
    case SOURCE_MANUAL_FINISH:
      Serial.print("M2 ");
      break;
  }

  print_uint64(events[index].time);
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

void command_process(char * cmd, uint64_t value, bool val_ok )
{
  if( strcasecmp(cmd, "time") == 0 )
  {
    if( val_ok )
    {
      ms_time = value;
    }
    Serial.print("N ");
    print_uint64(ms_time);
    Serial.println();
  }
  else if( strcasecmp(cmd, "ping") == 0 )
  {
    Serial.print("P ");
    print_uint64(val_ok ? value : 0);
    Serial.println();
  }
  else if( strcasecmp(cmd, "id") == 0 )
  {
    Serial.println("I RALLYX_TIMER");
  }
  else if( strcasecmp(cmd, "recall") == 0 )
  {
    if( val_ok && value < event_count && (event_count < EVENT_MAX || value >= event_count - EVENT_MAX) )
    {
      Serial.print("R ");
      print_event(value % EVENT_MAX);
      Serial.write(' ');
      Serial.println((uint32_t)value);
      //Serial.println("R M1 123345 123");
    }
    else
    {
      Serial.println("E bad value");
    }
  }
  else if( strcasecmp(cmd, "clear") == 0 )
  {
    event_count = 0;
    Serial.println("C 0");
  }
  else if( strcasecmp(cmd, "count") == 0 )
  {
    Serial.print("C ");
    Serial.println(event_count);
  }
  else if( strcasecmp(cmd, "max") == 0 )
  {
    Serial.print("M ");
    Serial.println(EVENT_MAX);
  }
  else if( strcasecmp(cmd, "debounce") == 0 )
  {
    if( val_ok )
    {
      debounce = (uint32_t)value;
      eeprom_write(ROM_OFFSET_DEBOUNCE, debounce);
    }
    Serial.print("B ");
    Serial.println(debounce);
  }
  else if( strcasecmp(cmd, "deadtime") == 0 )
  {
    if( val_ok )
    {
      deadtime = (uint32_t)value;
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
  uint64_t value;

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
          value = param != NULL ? strtoull(param, &endptr, 0) : 0;

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
  static uint64_t prev_time = 0;
  while( prev_time == ms_time );
  prev_time = ms_time;
}

void loop(void)
{
  static uint32_t count = 0;

  digitalWrite(PIN_LED, HIGH);

  if( count > event_count )
  {
    count = 0;
  }

  if( count < event_count )
  {
    Serial.print("T ");
    print_event(count % EVENT_MAX);
    Serial.write(' ');
    Serial.println(count);
    count++;
  }

  command_update();

  digitalWrite(PIN_LED, LOW);

  loop_wait();
}

