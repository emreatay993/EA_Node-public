.pragma library

function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
}

function approxEqual(a, b) {
    return Math.abs(Number(a) - Number(b)) <= 0.0001;
}

function minimumCropWidth(sourcePixelWidth) {
    return sourcePixelWidth > 0 ? (1.0 / sourcePixelWidth) : 0.001;
}

function minimumCropHeight(sourcePixelHeight) {
    return sourcePixelHeight > 0 ? (1.0 / sourcePixelHeight) : 0.001;
}

function fullCropRect() {
    return {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0};
}

function normalizedCropRect(x, y, w, h) {
    var left = Number(x);
    var top = Number(y);
    var widthValue = Number(w);
    var heightValue = Number(h);
    if (!isFinite(left) || !isFinite(top) || !isFinite(widthValue) || !isFinite(heightValue))
        return fullCropRect();
    if (!(widthValue > 0.0) || !(heightValue > 0.0))
        return fullCropRect();
    left = clamp(left, 0.0, 1.0);
    top = clamp(top, 0.0, 1.0);
    var right = clamp(left + widthValue, left, 1.0);
    var bottom = clamp(top + heightValue, top, 1.0);
    if (!(right > left) || !(bottom > top))
        return fullCropRect();
    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top
    };
}

function isFullCropRect(rect) {
    return approxEqual(rect.x, 0.0)
        && approxEqual(rect.y, 0.0)
        && approxEqual(rect.width, 1.0)
        && approxEqual(rect.height, 1.0);
}

function cropRectsEqual(a, b) {
    return approxEqual(Number(a.x || 0), Number(b.x || 0))
        && approxEqual(Number(a.y || 0), Number(b.y || 0))
        && approxEqual(Number(a.width || 0), Number(b.width || 0))
        && approxEqual(Number(a.height || 0), Number(b.height || 0));
}

function sourceClipRectFromNormalized(rect, sourcePixelWidth, sourcePixelHeight) {
    if (sourcePixelWidth <= 0 || sourcePixelHeight <= 0)
        return Qt.rect(0, 0, 0, 0);
    return Qt.rect(
        rect.x * sourcePixelWidth,
        rect.y * sourcePixelHeight,
        rect.width * sourcePixelWidth,
        rect.height * sourcePixelHeight
    );
}

function fitRect(containerWidth, containerHeight, sourceWidth, sourceHeight, fitMode) {
    var cw = Math.max(0.0, Number(containerWidth || 0));
    var ch = Math.max(0.0, Number(containerHeight || 0));
    var sw = Math.max(0.0, Number(sourceWidth || 0));
    var sh = Math.max(0.0, Number(sourceHeight || 0));
    if (!(cw > 0.0) || !(ch > 0.0) || !(sw > 0.0) || !(sh > 0.0))
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0};
    var normalizedMode = String(fitMode || "contain").trim().toLowerCase();
    if (normalizedMode === "original") {
        return {
            "x": (cw - sw) * 0.5,
            "y": (ch - sh) * 0.5,
            "width": sw,
            "height": sh
        };
    }
    var scale = normalizedMode === "cover"
        ? Math.max(cw / sw, ch / sh)
        : Math.min(cw / sw, ch / sh);
    var widthValue = sw * scale;
    var heightValue = sh * scale;
    return {
        "x": (cw - widthValue) * 0.5,
        "y": (ch - heightValue) * 0.5,
        "width": widthValue,
        "height": heightValue
    };
}

function containRect(containerWidth, containerHeight, sourceWidth, sourceHeight) {
    return fitRect(containerWidth, containerHeight, sourceWidth, sourceHeight, "contain");
}

function displayCropRect(x, y, w, h, imageRect) {
    var rect = normalizedCropRect(x, y, w, h);
    var widthValue = Number(imageRect.width || 0);
    var heightValue = Number(imageRect.height || 0);
    return {
        "x": Number(imageRect.x || 0) + rect.x * widthValue,
        "y": Number(imageRect.y || 0) + rect.y * heightValue,
        "width": rect.width * widthValue,
        "height": rect.height * heightValue
    };
}

function updatedDraftCropRect(
    handle,
    deltaPixelsX,
    deltaPixelsY,
    startX,
    startY,
    startW,
    startH,
    imageRect,
    sourcePixelWidth,
    sourcePixelHeight
) {
    var imageWidth = Number(imageRect.width || 0);
    var imageHeight = Number(imageRect.height || 0);
    if (!(imageWidth > 0.0) || !(imageHeight > 0.0))
        return normalizedCropRect(startX, startY, startW, startH);
    var deltaX = deltaPixelsX / imageWidth;
    var deltaY = deltaPixelsY / imageHeight;
    var left = Number(startX);
    var top = Number(startY);
    var right = Number(startX) + Number(startW);
    var bottom = Number(startY) + Number(startH);
    var minWidth = minimumCropWidth(sourcePixelWidth);
    var minHeight = minimumCropHeight(sourcePixelHeight);

    if (handle.indexOf("left") >= 0)
        left = clamp(left + deltaX, 0.0, right - minWidth);
    if (handle.indexOf("right") >= 0)
        right = clamp(right + deltaX, left + minWidth, 1.0);
    if (handle.indexOf("top") >= 0)
        top = clamp(top + deltaY, 0.0, bottom - minHeight);
    if (handle.indexOf("bottom") >= 0)
        bottom = clamp(bottom + deltaY, top + minHeight, 1.0);

    return normalizedCropRect(left, top, right - left, bottom - top);
}

function handleCursorShape(handle) {
    if (handle === "top_left" || handle === "bottom_right")
        return Qt.SizeFDiagCursor;
    if (handle === "top_right" || handle === "bottom_left")
        return Qt.SizeBDiagCursor;
    if (handle === "top" || handle === "bottom")
        return Qt.SizeVerCursor;
    return Qt.SizeHorCursor;
}

function handleX(handle, frameRect, handleSize) {
    var half = handleSize * 0.5;
    if (handle === "top_left" || handle === "left" || handle === "bottom_left")
        return frameRect.x - half;
    if (handle === "top_right" || handle === "right" || handle === "bottom_right")
        return frameRect.x + frameRect.width - half;
    return frameRect.x + frameRect.width * 0.5 - half;
}

function handleY(handle, frameRect, handleSize) {
    var half = handleSize * 0.5;
    if (handle === "top_left" || handle === "top" || handle === "top_right")
        return frameRect.y - half;
    if (handle === "bottom_left" || handle === "bottom" || handle === "bottom_right")
        return frameRect.y + frameRect.height - half;
    return frameRect.y + frameRect.height * 0.5 - half;
}
