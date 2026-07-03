import QuartzCore

struct MotionSpec {
    let enter: Double
    let exit: Double
    let easing: CAMediaTimingFunction
    let popScale: Double

    static func forPersonality(_ personality: Personality) -> MotionSpec {
        switch personality {
        case .playful:
            return MotionSpec(enter: 0.34, exit: 0.18, easing: CAMediaTimingFunction(controlPoints: 0.34, 1.56, 0.64, 1.0), popScale: 1.08)
        case .premium:
            return MotionSpec(enter: 0.52, exit: 0.28, easing: CAMediaTimingFunction(controlPoints: 0.4, 0.0, 0.2, 1.0), popScale: 1.0)
        case .corporate:
            return MotionSpec(enter: 0.32, exit: 0.20, easing: CAMediaTimingFunction(controlPoints: 0.2, 0.0, 0.0, 1.0), popScale: 1.01)
        case .energetic:
            return MotionSpec(enter: 0.22, exit: 0.12, easing: CAMediaTimingFunction(controlPoints: 0.16, 1.0, 0.3, 1.0), popScale: 1.16)
        }
    }
}

func normalized(_ seconds: Double, total: Double) -> NSNumber {
    NSNumber(value: min(1.0, max(0.0, seconds / max(total, 0.001))))
}
