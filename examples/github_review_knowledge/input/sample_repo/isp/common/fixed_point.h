#pragma once

#include <algorithm>
#include <cstdint>

namespace isp {

inline int16_t SaturateS16(int value) {
    return static_cast<int16_t>(std::clamp(value, -32768, 32767));
}

inline int RoundShift(int value, int shift) {
    if (shift <= 0) {
        return value;
    }
    const int bias = 1 << (shift - 1);
    return (value + bias) >> shift;
}

}  // namespace isp
