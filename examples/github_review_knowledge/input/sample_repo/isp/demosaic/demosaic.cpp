#include <cstdint>

namespace isp::demosaic {

void PlaceholderDemosaic(const uint16_t* input, uint16_t* output, int count) {
    for (int i = 0; i < count; ++i) {
        output[i] = input[i];
    }
}

}  // namespace isp::demosaic
