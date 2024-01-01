# PiicoDev Buzzer melody example. Define a melody as a combination of notes and durations.

from PiicoDev_Buzzer import PiicoDev_Buzzer
from PiicoDev_Unified import sleep_ms

# Define some note-frequency pairs
octave = 2
notes = {'C'  : octave * 262,
         'Db' : octave * 277,
         'D'  : octave * 294,
         'Eb' : octave * 311,
         'E'  : octave * 330,
         'F'  : octave * 349,
         'Gb' : octave * 370,
         'G'  : octave * 392,
         'Ab' : octave * 415,
         'A'  : octave * 440,
         'Bb' : octave * 466,
         'B'  : octave * 494,
         'Chi': octave * 523,
         'rest':0, # zero Hertz is the same as no tone at all
         }

# define a melody - two-dimensional list of notes and note-duration (ms)
melody = [['E',    500],
          ['D',    500],
          ['C',   500],
          ['rest', 500],
          ['E',    500],
          ['D',    500],
          ['C',   500],
          ['rest', 500],
          ['G',    500],
          ['F',    250],
          ['F',    250],
          ['E',    500],
          ['rest', 500],
          ['G',    500],
          ['F',    250],
          ['F',    250],
          ['E',    500],
          ['rest', 500],
          ]

buzz = PiicoDev_Buzzer(volume=2)

buzz.pwrLED(False)

# play the melody
for x in melody:
    note = x[0] # extract the note name
    duration = x[1] # extract the duration
    buzz.tone(notes[note], duration)
    sleep_ms(duration)