#include "alpha/Widget.h"

#include "beta/Helper.h"

namespace alpha {

int Widget::compute(int input) {
  beta::Helper helper;
  return helper.run(input);
}

}  // namespace alpha
