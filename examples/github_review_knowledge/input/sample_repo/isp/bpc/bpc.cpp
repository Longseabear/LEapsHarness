#include "isp/bpc/bpc.h"

#include <algorithm>

#include "isp/common/fixed_point.h"

namespace isp::bpc {

namespace {

uint16_t ReadClamped(const ImagePlane& plane, int x, int y) {
    const int cx = std::clamp(x, 0, plane.width - 1);
    const int cy = std::clamp(y, 0, plane.height - 1);
    return plane.input[cy * plane.stride + cx];
}

uint16_t CrossAverage(const ImagePlane& plane, int x, int y) {
    const int sum =
        ReadClamped(plane, x - 1, y) +
        ReadClamped(plane, x + 1, y) +
        ReadClamped(plane, x, y - 1) +
        ReadClamped(plane, x, y + 1);
    return static_cast<uint16_t>(isp::RoundShift(sum, 2));
}

bool IsOutlier(uint16_t center, uint16_t estimate, const BpcConfig& config) {
    const int delta_q8 = (static_cast<int>(center) - static_cast<int>(estimate)) << 8;
    return delta_q8 > config.hot_threshold_q8 || delta_q8 < -config.cold_threshold_q8;
}

}  // namespace

void CorrectBadPixels(const ImagePlane& plane, const BpcConfig& config) {
    for (int y = 0; y < plane.height; ++y) {
        for (int x = 0; x < plane.width; ++x) {
            const uint16_t center = ReadClamped(plane, x, y);
            const uint16_t estimate = CrossAverage(plane, x, y);
            const bool replace = config.enable_cross_check && IsOutlier(center, estimate, config);
            plane.output[y * plane.stride + x] = replace ? estimate : center;
        }
    }
}

}  // namespace isp::bpc
