# pending questions
format: 1
stage: design
round: 1
questions: 2

## question 1 [answered] (4 lines)
1. Which separator does the export write?
   Background: the request says CSV, and two of the tools that read it expect tabs.
   Options: A) comma (recommended) B) tab
   Blocks: the writer's interface

## answer 1 (1 lines)
A) comma

## question 2 [open] (4 lines)
2. Is the header row always written?
   Background: one reader drops the first line without looking at it.
   Options: A) always (recommended) B) behind a flag
   Blocks: the command's arguments

## report (13 lines)
## Report

The design cannot be finished until two decisions are made.

## Pending questions
1. Which separator does the export write?
   Background: the request says CSV, and two of the tools that read it expect tabs.
   Options: A) comma (recommended) B) tab
   Blocks: the writer's interface
2. Is the header row always written?
   Background: one reader drops the first line without looking at it.
   Options: A) always (recommended) B) behind a flag
   Blocks: the command's arguments
