#pragma once

namespace alpha {

// Wraps a single beta::Helper computation behind a stable name.
class Widget {
 public:
  int compute(int input);
};

}  // namespace alpha
