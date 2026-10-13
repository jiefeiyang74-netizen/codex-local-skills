// Package downloader handles Douyin video audio extraction.
// It uses Douyin's mobile web page to extract CDN URLs directly,
// without requiring yt-dlp, cookies, or browser signatures.
package downloader

import (
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	mobileUA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 Version/17.0 Mobile/15E148 Safari/604.1"
)

// routerDataPattern matches window._ROUTER_DATA in the HTML.
var routerDataPattern = regexp.MustCompile(`window\._ROUTER_DATA\s*=\s*(.*?)</script>`)

// wafChallengePattern matches Douyin's lightweight WAF proof-of-work challenge.
var wafChallengePattern = regexp.MustCompile(`wci="([^"]+)",cs="([^"]+)"`)

// VideoInfo contains extracted video metadata and URLs.
type VideoInfo struct {
	Title     string
	VideoURL  string
	AudioURL  string
	VideoURLs []string
	AudioURLs []string
}

// DownloadAudio extracts audio from a Douyin video and saves it locally.
// videoURL should be a canonical URL: https://www.douyin.com/video/<ID>
// outputDir is optional; if empty, a temp directory is used.
func DownloadAudio(videoURL string, outputDir string) (string, error) {
	// Extract video ID from URL
	videoID, err := extractVideoIDFromURL(videoURL)
	if err != nil {
		return "", fmt.Errorf("extracting video ID: %w", err)
	}

	// Fetch video info from mobile page
	info, err := FetchVideoInfo(videoID)
	if err != nil {
		return "", fmt.Errorf("fetching video info: %w", err)
	}

	// Prefer audio-only URLs, then try every video/CDN fallback returned by Douyin.
	downloadURLs := uniqueStrings(append(append(append(
		[]string{}, info.AudioURLs...), info.AudioURL), append(info.VideoURLs, info.VideoURL)...))
	if len(downloadURLs) == 0 {
		return "", fmt.Errorf("no downloadable URL found for video %s", videoID)
	}

	// Create output directory
	if outputDir == "" {
		outputDir, err = os.MkdirTemp("", "dyt-*")
		if err != nil {
			return "", fmt.Errorf("creating temp dir: %w", err)
		}
	}

	// Download the media file
	mediaPath := filepath.Join(outputDir, videoID+".mp4")
	var downloadErr error
	for sourceIndex, downloadURL := range downloadURLs {
		fmt.Fprintf(os.Stderr, "Downloading from CDN (source %d/%d)...\n", sourceIndex+1, len(downloadURLs))
		if err := downloadFile(downloadURL, mediaPath); err == nil {
			downloadErr = nil
			break
		} else {
			downloadErr = err
			os.Remove(mediaPath)
			fmt.Fprintf(os.Stderr, "CDN source %d failed: %v\n", sourceIndex+1, err)
		}
	}
	if downloadErr != nil {
		return "", fmt.Errorf("downloading media after %d sources: %w", len(downloadURLs), downloadErr)
	}

	// Extract audio with ffmpeg
	audioPath := filepath.Join(outputDir, videoID+".mp3")
	fmt.Fprintf(os.Stderr, "Extracting audio...\n")
	if err := extractAudio(mediaPath, audioPath); err != nil {
		return "", fmt.Errorf("extracting audio: %w", err)
	}

	// Clean up the video file
	os.Remove(mediaPath)

	return audioPath, nil
}

// FetchVideoInfo gets video metadata from Douyin's mobile web page.
// This approach does not require cookies, login, or browser signatures.
func FetchVideoInfo(videoID string) (*VideoInfo, error) {
	info, err := fetchVideoInfoFromSharePage(videoID)
	if err == nil {
		return info, nil
	}

	helper := strings.TrimSpace(os.Getenv("DYT_BROWSER_HELPER"))
	if helper == "" {
		return nil, err
	}

	fmt.Fprintf(os.Stderr, "Share page unavailable; trying browser fallback...\n")
	browserInfo, browserErr := fetchVideoInfoWithBrowser(videoID, helper)
	if browserErr != nil {
		return nil, fmt.Errorf("share page: %v; browser fallback: %w", err, browserErr)
	}
	return browserInfo, nil
}

func fetchVideoInfoFromSharePage(videoID string) (*VideoInfo, error) {
	shareURL := fmt.Sprintf("https://www.iesdouyin.com/share/video/%s", videoID)

	client := &http.Client{Timeout: 15 * time.Second, CheckRedirect: safeRedirect}
	req, err := http.NewRequest("GET", shareURL, nil)
	if err != nil {
		return nil, fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("User-Agent", mobileUA)

	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("fetching share page: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("reading response: %w", err)
	}

	html := string(body)
	if isWAFChallenge(html) {
		return nil, fmt.Errorf("verification required; no challenge solving in portable adapter")
	}

	// Extract _ROUTER_DATA JSON
	matches := routerDataPattern.FindStringSubmatch(html)
	if len(matches) < 2 {
		if strings.Contains(html, "验证码中间页") || strings.Contains(html, "TTGCaptcha") {
			return nil, fmt.Errorf("share page requires slider verification")
		}
		return nil, fmt.Errorf("_ROUTER_DATA not found in page (status %d, length %d)", resp.StatusCode, len(html))
	}

	rawJSON := strings.TrimSpace(matches[1])

	// Parse the top-level JSON
	var routerData map[string]json.RawMessage
	if err := json.Unmarshal([]byte(rawJSON), &routerData); err != nil {
		return nil, fmt.Errorf("parsing _ROUTER_DATA: %w", err)
	}

	// Navigate to loaderData -> "video_(id)/page" -> videoInfoRes -> item_list
	loaderRaw, ok := routerData["loaderData"]
	if !ok {
		return nil, fmt.Errorf("loaderData not found in _ROUTER_DATA")
	}

	var loaderData map[string]json.RawMessage
	if err := json.Unmarshal(loaderRaw, &loaderData); err != nil {
		return nil, fmt.Errorf("parsing loaderData: %w", err)
	}

	pageRaw, ok := loaderData["video_(id)/page"]
	if !ok {
		return nil, fmt.Errorf("video_(id)/page not found in loaderData")
	}

	var pageData map[string]json.RawMessage
	if err := json.Unmarshal(pageRaw, &pageData); err != nil {
		return nil, fmt.Errorf("parsing page data: %w", err)
	}

	videoInfoRaw, ok := pageData["videoInfoRes"]
	if !ok {
		keys := make([]string, 0, len(pageData))
		for key := range pageData {
			keys = append(keys, key)
		}
		return nil, fmt.Errorf("videoInfoRes not found in page data (keys: %s)", strings.Join(keys, ", "))
	}

	// Parse the video info structure
	var videoInfoRes struct {
		ItemList []struct {
			Desc  string `json:"desc"`
			Video struct {
				PlayAddr struct {
					URLList []string `json:"url_list"`
				} `json:"play_addr"`
			} `json:"video"`
		} `json:"item_list"`
	}
	if err := json.Unmarshal(videoInfoRaw, &videoInfoRes); err != nil {
		return nil, fmt.Errorf("parsing videoInfoRes: %w", err)
	}

	if len(videoInfoRes.ItemList) == 0 {
		return nil, fmt.Errorf("no items in video info response")
	}

	item := videoInfoRes.ItemList[0]
	info := &VideoInfo{
		Title: item.Desc,
	}

	// Get video URL and convert to watermark-free version
	if len(item.Video.PlayAddr.URLList) > 0 {
		for _, videoURL := range item.Video.PlayAddr.URLList {
			info.VideoURLs = append(info.VideoURLs, strings.Replace(videoURL, "playwm", "play", 1))
		}
		info.VideoURL = info.VideoURLs[0]
	}

	return info, nil
}

func fetchVideoInfoWithBrowser(videoID, helper string) (*VideoInfo, error) {
	nodeBin := strings.TrimSpace(os.Getenv("NODE_EXE"))
	if nodeBin == "" {
		nodeBin = "node"
	}

	cmd := exec.Command(nodeBin, helper, videoID)
	output, err := cmd.CombinedOutput()
	if err != nil {
		message := strings.TrimSpace(string(output))
		if message == "" {
			message = err.Error()
		}
		return nil, fmt.Errorf("browser media lookup failed: %s", message)
	}

	result, err := parseBrowserMediaResult(output)
	if err != nil {
		return nil, err
	}
	return result, nil
}

func parseBrowserMediaResult(output []byte) (*VideoInfo, error) {
	var result struct {
		Title     string   `json:"title"`
		VideoURL  string   `json:"videoUrl"`
		AudioURL  string   `json:"audioUrl"`
		VideoURLs []string `json:"videoUrls"`
		AudioURLs []string `json:"audioUrls"`
	}
	if err := json.Unmarshal(output, &result); err != nil {
		return nil, fmt.Errorf("parsing browser media result: %w", err)
	}
	if result.AudioURL == "" && result.VideoURL == "" {
		return nil, fmt.Errorf("browser media lookup returned no downloadable URL")
	}
	return &VideoInfo{
		Title:     result.Title,
		VideoURL:  result.VideoURL,
		AudioURL:  result.AudioURL,
		VideoURLs: result.VideoURLs,
		AudioURLs: result.AudioURLs,
	}, nil
}

func fetchSharePageWithCookie(client *http.Client, shareURL string, cookie *http.Cookie) (string, error) {
	req, err := http.NewRequest("GET", shareURL, nil)
	if err != nil {
		return "", fmt.Errorf("creating WAF retry request: %w", err)
	}
	req.Header.Set("User-Agent", mobileUA)
	req.AddCookie(cookie)

	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("fetching share page after WAF challenge: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("reading WAF retry response: %w", err)
	}
	return string(body), nil
}

func isWAFChallenge(html string) bool {
	return strings.Contains(html, "WAFJS") && wafChallengePattern.MatchString(html)
}

func solveWAFChallenge(html string) (*http.Cookie, error) {
	matches := wafChallengePattern.FindStringSubmatch(html)
	if len(matches) < 3 {
		return nil, fmt.Errorf("WAF challenge found but challenge data was not parseable")
	}

	raw, err := decodeBase64(matches[2])
	if err != nil {
		return nil, fmt.Errorf("decoding WAF challenge: %w", err)
	}

	var challenge struct {
		V struct {
			A string `json:"a"`
			B int64  `json:"b"`
			C string `json:"c"`
		} `json:"v"`
		S string `json:"s"`
	}
	if err := json.Unmarshal(raw, &challenge); err != nil {
		return nil, fmt.Errorf("parsing WAF challenge: %w", err)
	}

	prefix, err := decodeBase64(challenge.V.A)
	if err != nil {
		return nil, fmt.Errorf("decoding WAF prefix: %w", err)
	}
	expectedDigest, err := decodeBase64(challenge.V.C)
	if err != nil {
		return nil, fmt.Errorf("decoding WAF digest: %w", err)
	}
	expected := hex.EncodeToString(expectedDigest)

	var answer string
	for i := 0; i <= 1_000_000; i++ {
		candidate := strconv.Itoa(i)
		sum := sha256.Sum256(append(append([]byte{}, prefix...), []byte(candidate)...))
		if hex.EncodeToString(sum[:]) == expected {
			answer = candidate
			break
		}
	}
	if answer == "" {
		return nil, fmt.Errorf("WAF challenge answer not found")
	}

	payload := struct {
		V struct {
			A string `json:"a"`
			B int64  `json:"b"`
			C string `json:"c"`
		} `json:"v"`
		S string `json:"s"`
		D string `json:"d"`
	}{
		V: challenge.V,
		S: challenge.S,
		D: base64.StdEncoding.EncodeToString([]byte(answer)),
	}

	encodedPayload, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("encoding WAF answer: %w", err)
	}

	return &http.Cookie{
		Name:  matches[1],
		Value: base64.StdEncoding.EncodeToString(encodedPayload),
	}, nil
}

func decodeBase64(value string) ([]byte, error) {
	if decoded, err := base64.StdEncoding.DecodeString(value); err == nil {
		return decoded, nil
	}
	return base64.RawStdEncoding.DecodeString(value)
}

// downloadFile downloads a URL to a local file.
func downloadFile(url, destPath string) error {
	var lastErr error
	for attempt := 1; attempt <= 3; attempt++ {
		written, err := downloadFileOnce(url, destPath)
		if err == nil {
			fmt.Fprintf(os.Stderr, "Downloaded %.1f MB\n", float64(written)/(1024*1024))
			return nil
		}
		lastErr = err
		os.Remove(destPath)
		if attempt < 3 {
			fmt.Fprintf(os.Stderr, "CDN download attempt %d failed; retrying...\n", attempt)
			time.Sleep(time.Duration(attempt) * time.Second)
		}
	}
	return lastErr
}

func downloadFileOnce(url, destPath string) (int64, error) {
	if !safeMediaURL(url) { return 0, fmt.Errorf("unapproved media URL") }
	if curlBin, err := exec.LookPath("curl"); err == nil {
		cmd := exec.Command(curlBin,
			"--silent", "--show-error", "--location", "--fail",
			"--proto", "=https", "--proto-redir", "=https", "--max-redirs", "0",
			"--connect-timeout", "20", "--max-time", "300",
			"--user-agent", mobileUA,
			"--referer", "https://www.douyin.com/",
			"--output", destPath,
			url,
		)
		if output, err := cmd.CombinedOutput(); err != nil {
			message := strings.TrimSpace(string(output))
			if message == "" {
				message = err.Error()
			}
			return 0, fmt.Errorf("curl download failed: %s", message)
		}
		info, err := os.Stat(destPath)
		if err != nil {
			return 0, fmt.Errorf("checking curl output: %w", err)
		}
		if info.Size() == 0 {
			return 0, fmt.Errorf("curl returned an empty file")
		}
		return info.Size(), nil
	}

	return downloadFileOnceHTTP(url, destPath)
}

func downloadFileOnceHTTP(url, destPath string) (int64, error) {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.DisableCompression = true
	if !safeMediaURL(url) { return 0, fmt.Errorf("unapproved media URL") }
	client := &http.Client{Timeout: 5 * time.Minute, Transport: transport, CheckRedirect: safeRedirect}

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return 0, fmt.Errorf("creating request: %w", err)
	}
	req.Header.Set("User-Agent", mobileUA)
	req.Header.Set("Referer", "https://www.douyin.com/")
	req.Header.Set("Accept", "*/*")
	req.Header.Set("Accept-Encoding", "identity")
	req.Close = true

	resp, err := client.Do(req)
	if err != nil {
		return 0, fmt.Errorf("downloading: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		return 0, fmt.Errorf("download failed with status %d", resp.StatusCode)
	}

	out, err := os.Create(destPath)
	if err != nil {
		return 0, fmt.Errorf("creating file: %w", err)
	}
	written, copyErr := io.Copy(out, resp.Body)
	closeErr := out.Close()
	if copyErr != nil {
		return written, fmt.Errorf("writing file: %w", copyErr)
	}
	if closeErr != nil {
		return written, fmt.Errorf("closing file: %w", closeErr)
	}
	if written == 0 {
		return 0, fmt.Errorf("download returned an empty file")
	}
	return written, nil
}

func uniqueStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

// extractAudio extracts audio from a media file using ffmpeg.
func extractAudio(inputPath, outputPath string) error {
	cmd := exec.Command("ffmpeg", "-y", "-i", inputPath,
		"-vn", "-acodec", "libmp3lame", "-ab", "128k", outputPath)
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("ffmpeg failed: %w\nOutput: %s", err, string(out))
	}
	return nil
}

func extractVideoIDFromURL(videoURL string) (string, error) {
	parts := strings.Split(strings.TrimRight(videoURL, "/"), "/")
	for i, p := range parts {
		if p == "video" && i+1 < len(parts) {
			return parts[i+1], nil
		}
	}
	return "", fmt.Errorf("cannot extract video ID from: %s", videoURL)
}

// Cleanup removes the temporary directory for a downloaded audio file.
func Cleanup(audioPath string) {
	dir := filepath.Dir(audioPath)
	base := filepath.Base(dir)
	// Only remove directories that match our naming convention
	if strings.HasPrefix(base, "dyt-") {
		os.RemoveAll(dir)
	}
}

// CheckDependencies verifies that ffmpeg is available.
// yt-dlp is no longer required.
func CheckDependencies() error {
	if _, err := exec.LookPath("ffmpeg"); err != nil {
		return fmt.Errorf("ffmpeg not found: install with 'brew install ffmpeg'")
	}
	return nil
}
