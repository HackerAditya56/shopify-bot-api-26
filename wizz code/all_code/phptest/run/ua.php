<?php
/**
 * User-Agent string generator.
 *
 * index.php requires this at line 111 and uses the returned string in five
 * curl User-Agent headers. The value is generated once per request and reused
 * across the whole checkout so the session fingerprint stays internally
 * consistent — a single UA for cart, checkout, proposal, submit and poll.
 */

class userAgent
{
    /** @var string|null Cached per-platform result so one request yields one UA. */
    private $cache = [];

    /**
     * Returns a desktop browser User-Agent for the requested platform.
     *
     * @param string $platform One of: windows, mac, linux, android, ios
     * @return string
     */
    public function generate($platform = 'windows')
    {
        $platform = strtolower(trim((string) $platform));

        if (isset($this->cache[$platform])) {
            return $this->cache[$platform];
        }

        $version = $this->chromeVersion();

        switch ($platform) {
            case 'mac':
            case 'macos':
            case 'osx':
                $os = 'Macintosh; Intel Mac OS X 10_15_7';
                break;

            case 'linux':
                $os = 'X11; Linux x86_64';
                break;

            case 'android':
                $os = 'Linux; Android 14; Pixel 8';
                break;

            case 'ios':
            case 'iphone':
                $os = 'iPhone; CPU iPhone OS 17_5 like Mac OS X';
                break;

            case 'windows':
            default:
                $os = 'Windows NT 10.0; Win64; x64';
                break;
        }

        $ua = sprintf(
            'Mozilla/5.0 (%s) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/%s Safari/537.36',
            $os,
            $version
        );

        $this->cache[$platform] = $ua;
        return $ua;
    }

    /**
     * Picks a Chrome major version from the set currently deployed.
     *
     * @return string
     */
    private function chromeVersion()
    {
        $versions = ['126.0.0.0', '127.0.0.0', '128.0.0.0', '129.0.0.0'];
        return $versions[array_rand($versions)];
    }
}
