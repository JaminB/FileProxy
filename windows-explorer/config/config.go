// Package config loads and saves the application configuration.
package config

import (
	"encoding/json"
	"os"
	"path/filepath"
)

// Config holds the user's server URL and API key.
type Config struct {
	ServerURL string `json:"server_url"`
	APIKey    string `json:"api_key"`
}

func configPath() (string, error) {
	dir, err := os.UserConfigDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "FileProxyExplorer", "config.json"), nil
}

// Load reads the config from disk. Returns an empty Config on any error.
func Load() Config {
	p, err := configPath()
	if err != nil {
		return Config{}
	}
	data, err := os.ReadFile(p) // #nosec G304 — path is UserConfigDir + hardcoded suffix
	if err != nil {
		return Config{}
	}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {
		return Config{}
	}
	return cfg
}

// Save writes the config to disk at %APPDATA%\FileProxyExplorer\config.json.
func Save(cfg Config) error {
	p, err := configPath()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(p, data, 0600)
}
