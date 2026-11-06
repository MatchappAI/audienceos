// AudienceOS OCR helper: on-device text recognition with Apple's Vision framework.
// Usage: ocr <image-or-pdf> [page,page,...]   (pages are 1-based; PDF only; default = all pages)
// Prints JSON: {"pages":[{"page":1,"text":"…","confidence":0.93}]} or {"error":"…"} (exit 1).
// Nothing leaves the Mac: Vision runs locally.
import CoreGraphics
import Foundation
import ImageIO
import Vision

func fail(_ msg: String) -> Never {
    let out = try! JSONSerialization.data(withJSONObject: ["error": msg])
    FileHandle.standardOutput.write(out)
    exit(1)
}

func recognize(_ image: CGImage) -> (String, Double) {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = true
    req.automaticallyDetectsLanguage = true
    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    do { try handler.perform([req]) } catch { return ("", 0) }
    let obs = req.results ?? []
    var lines: [String] = []
    var conf = 0.0
    for o in obs {
        if let c = o.topCandidates(1).first {
            lines.append(c.string)
            conf += Double(c.confidence)
        }
    }
    return (lines.joined(separator: "\n"), obs.isEmpty ? 0 : conf / Double(obs.count))
}

func renderPDFPage(_ page: CGPDFPage) -> CGImage? {
    let box = page.getBoxRect(.mediaBox)
    let scale: CGFloat = 2.5  // ~180 dpi: good recognition, bounded memory
    let w = Int(box.width * scale), h = Int(box.height * scale)
    guard w > 0, h > 0, w * h < 60_000_000,
          let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.scaleBy(x: scale, y: scale)
    ctx.translateBy(x: -box.origin.x, y: -box.origin.y)
    ctx.drawPDFPage(page)
    return ctx.makeImage()
}

let args = CommandLine.arguments
guard args.count >= 2 else { fail("usage: ocr <file> [pages]") }
let url = URL(fileURLWithPath: args[1])
let wanted: Set<Int>? = args.count >= 3 ? Set(args[2].split(separator: ",").compactMap { Int($0) }) : nil
var pages: [[String: Any]] = []

if url.pathExtension.lowercased() == "pdf" {
    guard let doc = CGPDFDocument(url as CFURL) else { fail("cannot open PDF") }
    if doc.numberOfPages > 0 {
        for i in 1...doc.numberOfPages {
            if let w = wanted, !w.contains(i) { continue }
            guard let p = doc.page(at: i), let img = renderPDFPage(p) else { continue }
            let (t, c) = recognize(img)
            pages.append(["page": i, "text": t, "confidence": c])
        }
    }
} else {
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else { fail("cannot open image") }
    let (t, c) = recognize(img)
    pages.append(["page": 1, "text": t, "confidence": c])
}
FileHandle.standardOutput.write(try! JSONSerialization.data(withJSONObject: ["pages": pages]))
