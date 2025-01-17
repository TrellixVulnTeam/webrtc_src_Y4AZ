// Copyright 2014 the V8 project authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include <limits>

#include "src/flags.h"
#include "src/heap/memory-reducer.h"
#include "testing/gtest/include/gtest/gtest.h"

namespace v8 {
namespace internal {

MemoryReducer::State DoneState() {
  return MemoryReducer::State(MemoryReducer::kDone, 0, 0.0);
}


MemoryReducer::State WaitState(int started_gcs, double next_gc_start_ms) {
  return MemoryReducer::State(MemoryReducer::kWait, started_gcs,
                              next_gc_start_ms);
}


MemoryReducer::State RunState(int started_gcs, double next_gc_start_ms) {
  return MemoryReducer::State(MemoryReducer::kRun, started_gcs,
                              next_gc_start_ms);
}


MemoryReducer::Event MarkCompactEvent(double time_ms,
                                      bool next_gc_likely_to_collect_more) {
  MemoryReducer::Event event;
  event.type = MemoryReducer::kMarkCompact;
  event.time_ms = time_ms;
  event.next_gc_likely_to_collect_more = next_gc_likely_to_collect_more;
  return event;
}


MemoryReducer::Event MarkCompactEventGarbageLeft(double time_ms) {
  return MarkCompactEvent(time_ms, true);
}


MemoryReducer::Event MarkCompactEventNoGarbageLeft(double time_ms) {
  return MarkCompactEvent(time_ms, false);
}


MemoryReducer::Event TimerEvent(double time_ms, bool low_allocation_rate,
                                bool can_start_incremental_gc) {
  MemoryReducer::Event event;
  event.type = MemoryReducer::kTimer;
  event.time_ms = time_ms;
  event.low_allocation_rate = low_allocation_rate;
  event.can_start_incremental_gc = can_start_incremental_gc;
  return event;
}


MemoryReducer::Event TimerEventLowAllocationRate(double time_ms) {
  return TimerEvent(time_ms, true, true);
}


MemoryReducer::Event TimerEventHighAllocationRate(double time_ms) {
  return TimerEvent(time_ms, false, true);
}


MemoryReducer::Event TimerEventPendingGC(double time_ms) {
  return TimerEvent(time_ms, true, false);
}


MemoryReducer::Event ContextDisposedEvent(double time_ms) {
  MemoryReducer::Event event;
  event.type = MemoryReducer::kContextDisposed;
  event.time_ms = time_ms;
  return event;
}


MemoryReducer::Event BackgroundIdleNotificationEvent(
    double time_ms, bool can_start_incremental_gc = true) {
  MemoryReducer::Event event;
  event.type = MemoryReducer::kBackgroundIdleNotification;
  event.time_ms = time_ms;
  event.can_start_incremental_gc = can_start_incremental_gc;
  return event;
}


TEST(MemoryReducer, FromDoneToDone) {
  MemoryReducer::State state0(DoneState()), state1(DoneState());

  state1 = MemoryReducer::Step(state0, TimerEventLowAllocationRate(0));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);

  state1 = MemoryReducer::Step(state0, TimerEventHighAllocationRate(0));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);

  state1 = MemoryReducer::Step(state0, TimerEventPendingGC(0));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);

  state1 = MemoryReducer::Step(state0, BackgroundIdleNotificationEvent(0));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);
}


TEST(MemoryReducer, FromDoneToWait) {
  if (!FLAG_incremental_marking) return;

  MemoryReducer::State state0(DoneState()), state1(DoneState());

  state1 = MemoryReducer::Step(state0, MarkCompactEventGarbageLeft(0));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, MarkCompactEventNoGarbageLeft(0));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, ContextDisposedEvent(0));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);
}


TEST(MemoryReducer, FromWaitToWait) {
  if (!FLAG_incremental_marking) return;

  MemoryReducer::State state0(WaitState(2, 1000.0)), state1(DoneState());

  state1 = MemoryReducer::Step(state0, ContextDisposedEvent(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(
      state0, TimerEventLowAllocationRate(state0.next_gc_start_ms - 1));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, TimerEventHighAllocationRate(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(2000 + MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, TimerEventPendingGC(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(2000 + MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, MarkCompactEventGarbageLeft(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(2000 + MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, MarkCompactEventNoGarbageLeft(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(2000 + MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, BackgroundIdleNotificationEvent(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(2000 + MemoryReducer::kLongDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs + 1, state1.started_gcs);

  state1 =
      MemoryReducer::Step(state0, BackgroundIdleNotificationEvent(2000, false));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state0.started_gcs = MemoryReducer::kMaxNumberOfGCs;
  state1 = MemoryReducer::Step(state0, BackgroundIdleNotificationEvent(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);
}


TEST(MemoryReducer, FromWaitToRun) {
  if (!FLAG_incremental_marking) return;

  MemoryReducer::State state0(WaitState(0, 1000.0)), state1(DoneState());

  state1 = MemoryReducer::Step(
      state0, TimerEventLowAllocationRate(state0.next_gc_start_ms + 1));
  EXPECT_EQ(MemoryReducer::kRun, state1.action);
  EXPECT_EQ(0, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs + 1, state1.started_gcs);
}


TEST(MemoryReducer, FromWaitToDone) {
  if (!FLAG_incremental_marking) return;

  MemoryReducer::State state0(WaitState(2, 0.0)), state1(DoneState());

  state0.started_gcs = MemoryReducer::kMaxNumberOfGCs;

  state1 = MemoryReducer::Step(state0, TimerEventLowAllocationRate(2000));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);
  EXPECT_EQ(0, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, TimerEventHighAllocationRate(2000));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);
  EXPECT_EQ(0, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, TimerEventPendingGC(2000));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);
  EXPECT_EQ(0, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);
}


TEST(MemoryReducer, FromRunToRun) {
  if (!FLAG_incremental_marking) return;

  MemoryReducer::State state0(RunState(1, 0.0)), state1(DoneState());

  state1 = MemoryReducer::Step(state0, TimerEventLowAllocationRate(2000));
  EXPECT_EQ(MemoryReducer::kRun, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, TimerEventHighAllocationRate(2000));
  EXPECT_EQ(MemoryReducer::kRun, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, TimerEventPendingGC(2000));
  EXPECT_EQ(MemoryReducer::kRun, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state1 = MemoryReducer::Step(state0, ContextDisposedEvent(2000));
  EXPECT_EQ(MemoryReducer::kRun, state1.action);
  EXPECT_EQ(state0.next_gc_start_ms, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);
}


TEST(MemoryReducer, FromRunToDone) {
  if (!FLAG_incremental_marking) return;

  MemoryReducer::State state0(RunState(2, 0.0)), state1(DoneState());

  state1 = MemoryReducer::Step(state0, MarkCompactEventNoGarbageLeft(2000));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);
  EXPECT_EQ(0, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);

  state0.started_gcs = MemoryReducer::kMaxNumberOfGCs;

  state1 = MemoryReducer::Step(state0, MarkCompactEventGarbageLeft(2000));
  EXPECT_EQ(MemoryReducer::kDone, state1.action);
  EXPECT_EQ(0, state1.next_gc_start_ms);
  EXPECT_EQ(0, state1.started_gcs);
}


TEST(MemoryReducer, FromRunToWait) {
  if (!FLAG_incremental_marking) return;

  MemoryReducer::State state0(RunState(2, 0.0)), state1(DoneState());

  state1 = MemoryReducer::Step(state0, MarkCompactEventGarbageLeft(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(2000 + MemoryReducer::kShortDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);

  state0.started_gcs = 1;

  state1 = MemoryReducer::Step(state0, MarkCompactEventNoGarbageLeft(2000));
  EXPECT_EQ(MemoryReducer::kWait, state1.action);
  EXPECT_EQ(2000 + MemoryReducer::kShortDelayMs, state1.next_gc_start_ms);
  EXPECT_EQ(state0.started_gcs, state1.started_gcs);
}

}  // namespace internal
}  // namespace v8
