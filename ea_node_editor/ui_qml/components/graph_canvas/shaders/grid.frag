#version 440
// Rebuild with scripts/build_canvas_grid_shader.ps1; never edit the .qsb by hand.
layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    vec2 viewportSize;
    vec2 minorOffset;
    vec2 majorOffset;
    vec4 minorGridColor;
    vec4 majorGridColor;
    float minorStep;
    float majorStep;
    float minorPointSize;
    float majorPointSize;
    float devicePixelRatio;
    float pointStyle;
};

float coverage(vec2 position, vec2 offset, float stepSize, float pointSize) {
    // Reduce the origin modulo the period in QML (double precision), before
    // passing it to the GPU. Large/negative world coordinates stay stable.
    vec2 distanceToGrid = abs(mod(position - offset + stepSize * 0.5,
                                 stepSize) - stepSize * 0.5) * devicePixelRatio;
    float halfWidth = mix(1.0, pointSize, pointStyle) * 0.5;
    // Pixel-area coverage, rather than rounding each mark independently, keeps
    // one-pixel lines and small square dots smooth during fractional movement.
    vec2 covered = clamp(vec2(halfWidth + 0.5) - distanceToGrid, 0.0, 1.0);
    return mix(max(covered.x, covered.y), covered.x * covered.y, pointStyle);
}

void main() {
    vec2 position = qt_TexCoord0 * viewportSize;
    vec4 minor = minorGridColor * coverage(position, minorOffset, minorStep, minorPointSize);
    vec4 major = majorGridColor * coverage(position, majorOffset, majorStep, majorPointSize);
    fragColor = (major + minor * (1.0 - major.a)) * qt_Opacity;
}
