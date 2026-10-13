// Local-only portable adapter. Upstream core: see LICENSE and ../NOTICE.md.
package main

import (
 "flag"
 "fmt"
 "os"
 "path/filepath"
 "github.com/vangie/douyin-transcriber/internal/downloader"
 "github.com/vangie/douyin-transcriber/internal/resolver"
 "github.com/vangie/douyin-transcriber/internal/transcriber"
)

func main() {
 model := flag.String("model-path", "", "Required small ggml model")
 output := flag.String("o", "", "Transcript output")
 language := flag.String("l", "zh", "Language")
 audio := flag.String("audio", "", "Explicit local audio fixture/input")
 flag.String("prompt", "", "Accepted for legacy API compatibility; no forced vocabulary")
 flag.Bool("local", true, "Local mode only")
 flag.Bool("keep-audio", true, "Always retains audio")
 flag.Parse()
 if err := run(*model, *output, *language, *audio); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
}
func run(model, output, language, audio string) error {
 if model == "" || output == "" || language != "zh" { return fmt.Errorf("model-path, output and zh are required") }
 var err error
 if audio == "" {
  if flag.NArg() != 1 { return fmt.Errorf("one Douyin URL is required") }
  var url string
  url, err = resolver.Resolve(flag.Arg(0)); if err != nil { return err }
  audio, err = downloader.DownloadAudio(url, filepath.Dir(output)); if err != nil { return err }
 }
 fmt.Fprintf(os.Stderr, "Audio saved: %s\n", audio)
 text, err := transcriber.TranscribeLocal(audio, transcriber.LocalOptions{ModelPath:model, Language:language})
 if err != nil { return err }
 return os.WriteFile(output, []byte(text+"\n"), 0600)
}
