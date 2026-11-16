# Asset Caching Strategy & Resolution Matrix

## Resolution Tiers
- **Thumbnail / Mobile**: 480x270 (WebP, ~35KB)
- **Standard Desktop**: 1280x720 (WebP, ~180KB)
- **Retina 4K Banner**: 2560x1440 (WebP, ~450KB)

## Cache Key Computation
Cache keys are derived from:
`SHA256(CommitCount + StreakDays + TopLanguage + WeatherSeed)`
Unchanged keys serve cached renders instantly from CDN storage.
