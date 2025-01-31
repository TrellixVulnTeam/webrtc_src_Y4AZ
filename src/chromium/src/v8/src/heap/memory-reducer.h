// Copyright 2015 the V8 project authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef V8_HEAP_memory_reducer_H
#define V8_HEAP_memory_reducer_H

#include "include/v8-platform.h"
#include "src/base/macros.h"

namespace v8 {
namespace internal {

class Heap;


// The goal of the MemoryReducer class is to detect transition of the mutator
// from high allocation phase to low allocation phase and to collect potential
// garbage created in the high allocation phase.
//
// The class implements an automaton with the following states and transitions.
//
// States:
// - DONE
// - WAIT <started_gcs> <next_gc_start_ms>
// - RUN <started_gcs>
// The <started_gcs> is an integer in range from 0..kMaxNumberOfGCs that stores
// the number of GCs initiated by the MemoryReducer since it left the DONE
// state.
// The <next_gc_start_ms> is a double that stores the earliest time the next GC
// can be initiated by the MemoryReducer.
// The DONE state means that the MemoryReducer is not active.
// The WAIT state means that the MemoryReducer is waiting for mutator allocation
// rate to drop. The check for the allocation rate happens in the timer task
// callback.
// The RUN state means that the MemoryReducer started incremental marking and is
// waiting for it to finish. Incremental marking steps are performed as usual
// in the idle notification and in the mutator.
//
// Transitions:
// DONE -> WAIT 0 (now_ms + long_delay_ms) happens:
//     - on context disposal,
//     - at the end of mark-compact GC initiated by the mutator.
// This signals that there is potential garbage to be collected.
//
// WAIT n x -> WAIT n (now_ms + long_delay_ms) happens:
//     - on mark-compact GC initiated by the mutator,
//     - in the timer callback if the mutator allocation rate is high or
//       incremental GC is in progress.
//
// WAIT n x -> WAIT (n+1) happens:
//     - on background idle notification, which signals that we can start
//       incremental marking even if the allocation rate is high.
// The MemoryReducer starts incremental marking on this transition but still
// has a pending timer task.
//
// WAIT n x -> DONE happens:
//     - in the timer callback if n >= kMaxNumberOfGCs.
//
// WAIT n x -> RUN (n+1) happens:
//     - in the timer callback if the mutator allocation rate is low
//       and now_ms >= x and there is no incremental GC in progress.
// The MemoryReducer starts incremental marking on this transition.
//
// RUN n -> DONE happens:
//     - at end of the incremental GC initiated by the MemoryReducer if
//       (n > 1 and there is no more garbage to be collected) or
//       n == kMaxNumberOfGCs.
// RUN n -> WAIT n (now_ms + short_delay_ms) happens:
//     - at end of the incremental GC initiated by the MemoryReducer if
//       (n == 1 or there is more garbage to be collected) and
//       n < kMaxNumberOfGCs.
//
// now_ms is the current time, long_delay_ms and short_delay_ms are constants.
class MemoryReducer {
 public:
  enum Action { kDone, kWait, kRun };

  struct State {
    State(Action action, int started_gcs, double next_gc_start_ms)
        : action(action),
          started_gcs(started_gcs),
          next_gc_start_ms(next_gc_start_ms) {}
    Action action;
    int started_gcs;
    double next_gc_start_ms;
  };

  enum EventType {
    kTimer,
    kMarkCompact,
    kContextDisposed,
    kBackgroundIdleNotification
  };

  struct Event {
    EventType type;
    double time_ms;
    bool low_allocation_rate;
    bool next_gc_likely_to_collect_more;
    bool can_start_incremental_gc;
  };

  explicit MemoryReducer(Heap* heap) : heap_(heap), state_(kDone, 0, 0.0) {}
  // Callbacks.
  void NotifyTimer(const Event& event);
  void NotifyMarkCompact(const Event& event);
  void NotifyContextDisposed(const Event& event);
  void NotifyBackgroundIdleNotification(const Event& event);
  // The step function that computes the next state from the current state and
  // the incoming event.
  static State Step(const State& state, const Event& event);
  // Posts a timer task that will call NotifyTimer after the given delay.
  void ScheduleTimer(double delay_ms);

  static const int kLongDelayMs;
  static const int kShortDelayMs;
  static const int kMaxNumberOfGCs;

  Heap* heap() { return heap_; }

 private:
  class TimerTask : public v8::Task {
   public:
    explicit TimerTask(MemoryReducer* memory_reducer)
        : memory_reducer_(memory_reducer) {}
    virtual ~TimerTask() {}

   private:
    // v8::Task overrides.
    void Run() override;
    MemoryReducer* memory_reducer_;
    DISALLOW_COPY_AND_ASSIGN(TimerTask);
  };

  Heap* heap_;
  State state_;

  DISALLOW_COPY_AND_ASSIGN(MemoryReducer);
};

}  // namespace internal
}  // namespace v8

#endif  // V8_HEAP_memory_reducer_H
