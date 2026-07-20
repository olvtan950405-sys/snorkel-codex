#!/usr/bin/env bash
set -euo pipefail

cat > /app/lib/forgegate.rb <<'RUBY'
# frozen_string_literal: true

require 'base64'
require 'digest'
require 'fileutils'
require 'json'
require 'openssl'
require 'time'

module ForgeGate
  module_function

  DIGEST = /\Asha256:([0-9a-f]{64})\z/
  INSTANT = /\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\z/
  INDEX_MT = 'application/vnd.oci.image.index.v1+json'
  MANIFEST_MT = 'application/vnd.oci.image.manifest.v1+json'
  CONFIG_MT = 'application/vnd.oci.image.config.v1+json'
  LAYER_MTS = ['application/vnd.oci.image.layer.v1.tar',
               'application/vnd.oci.image.layer.v1.tar+gzip'].freeze
  REASON_ORDER = %w[SUBJECT_MISMATCH SIGNATURE_POLICY_UNMET BUILDER_NOT_ALLOWED
                    SOURCE_NOT_ALLOWED REF_NOT_ALLOWED COMMIT_INVALID BUILD_TIME_INVALID
                    MATERIAL_NOT_TRUSTED VULNERABILITY_UNWAIVED].freeze

  def run(argv)
    return usage unless argv.shift == 'evaluate'
    options = parse_options(argv)
    return usage unless %w[layout policy keyring waivers out].all? { |key| options[key] }

    policy = read_json(options['policy'])
    keyring = read_json(options['keyring'])
    waivers = read_json(options['waivers'])
    validate_policy(policy)
    validate_keyring(keyring)
    validate_waivers(waivers)
    index_bytes, selected = validate_layout(options['layout'], policy)

    platforms = selected.map do |platform, descriptor|
      evaluate_platform(platform, descriptor, options['layout'], policy, keyring, waivers)
    end.sort_by { |item| item['platform'].b }
    write_output(options['out'], policy['image'], digest(index_bytes), platforms)
    0
  rescue StandardError
    begin
      image = policy.is_a?(Hash) ? policy['image'] : nil
      write_invalid(options && options['out'], image)
      0
    rescue StandardError
      2
    end
  end

  def parse_options(argv)
    result = {}
    until argv.empty?
      flag = argv.shift
      return {} unless flag&.match?(/\A--(layout|policy|keyring|waivers|out)\z/) && !argv.empty?
      key = flag.delete_prefix('--')
      return {} if result.key?(key)
      result[key] = argv.shift
    end
    result
  end

  def read_json(path)
    JSON.parse(File.binread(path), create_additions: false)
  end

  def exact!(value, keys)
    raise 'not an object' unless value.is_a?(Hash)
    raise 'schema mismatch' unless value.keys.sort == keys.sort
  end

  def instant(value)
    raise 'bad instant' unless value.is_a?(String) && value.match?(INSTANT)
    Time.iso8601(value)
  end

  def validate_policy(policy)
    exact!(policy, %w[allowed_builders evaluation_time image platforms role_minimums
                      signature_threshold trusted_material_prefixes])
    instant(policy['evaluation_time'])
    raise unless policy['image'].is_a?(String) && !policy['image'].empty?
    raise unless policy['signature_threshold'].is_a?(Integer) && policy['signature_threshold'].positive?
    raise unless policy['role_minimums'].is_a?(Hash) && !policy['role_minimums'].empty?
    raise unless policy['role_minimums'].all? { |k, v| k.is_a?(String) && !k.empty? && v.is_a?(Integer) && v.positive? }
    raise unless unique_array?(policy['trusted_material_prefixes']) { |x| x.is_a?(String) && !x.empty? }
    raise unless unique_array?(policy['platforms']) { |x| valid_platform?(x) }
    ids = []
    raise unless policy['allowed_builders'].is_a?(Array) && policy['allowed_builders'].all? do |entry|
      exact!(entry, %w[builder_id source_prefix ref_glob])
      good = entry.values.all? { |x| x.is_a?(String) && !x.empty? }
      ids << entry['builder_id']
      good
    end
    raise unless ids.uniq.length == ids.length
  end

  def validate_keyring(keyring)
    exact!(keyring, ['keys'])
    ids = []
    raise unless keyring['keys'].is_a?(Array) && keyring['keys'].all? do |key|
      exact!(key, %w[key_id builder_id role public_key_pem active_from active_until revoked_at])
      ids << key['key_id']
      %w[key_id builder_id role public_key_pem].all? { |name| key[name].is_a?(String) && !key[name].empty? } &&
        [key['active_from'], key['active_until'], key['revoked_at']].all? { |x| x.nil? || (instant(x); true) } &&
        !key['active_from'].nil?
    end
    raise unless ids.uniq.length == ids.length
  end

  def validate_waivers(document)
    exact!(document, ['waivers'])
    ids = []
    raise unless document['waivers'].is_a?(Array) && document['waivers'].all? do |item|
      exact!(item, %w[id image platform advisory package builder_id source_prefix commit starts_at expires_at])
      ids << item['id']
      required = %w[id image platform advisory package builder_id source_prefix starts_at expires_at]
      required.all? { |name| item[name].is_a?(String) && !item[name].empty? } &&
        (item['commit'].nil? || item['commit'].match?(/\A[0-9a-f]{40}\z/)) &&
        (instant(item['starts_at']); instant(item['expires_at']); true)
    end
    raise unless ids.uniq.length == ids.length
  end

  def unique_array?(value)
    return false unless value.is_a?(Array) && value.all? { |x| yield(x) }
    value.map { |x| canonical(x) }.uniq.length == value.length
  end

  def valid_platform?(platform)
    return false unless platform.is_a?(Hash)
    wanted = platform.key?('variant') ? %w[architecture os variant] : %w[architecture os]
    platform.keys.sort == wanted.sort && platform.values.all? { |x| x.is_a?(String) && !x.empty? }
  end

  def platform_name(platform)
    [platform['os'], platform['architecture'], platform['variant']].compact.join('-')
  end

  def validate_layout(layout, policy)
    layout_doc = read_json(File.join(layout, 'oci-layout'))
    exact!(layout_doc, ['imageLayoutVersion'])
    raise unless layout_doc['imageLayoutVersion'] == '1.0.0'
    index_bytes = File.binread(File.join(layout, 'index.json'))
    index = JSON.parse(index_bytes)
    exact!(index, %w[schemaVersion mediaType manifests])
    raise unless index['schemaVersion'] == 2 && index['mediaType'] == INDEX_MT && index['manifests'].is_a?(Array)

    by_platform = {}
    manifest_digests = []
    index['manifests'].each do |descriptor|
      exact!(descriptor, %w[mediaType digest size platform])
      raise unless descriptor['mediaType'] == MANIFEST_MT && valid_platform?(descriptor['platform'])
      name = platform_name(descriptor['platform'])
      raise if by_platform.key?(name)
      bytes = blob(layout, descriptor)
      manifest_digests << descriptor['digest']
      validate_manifest(layout, bytes, descriptor['platform'])
      by_platform[name] = descriptor
    end
    raise unless manifest_digests.uniq.length == manifest_digests.length
    requested = policy['platforms'].map { |p| platform_name(p) }
    raise unless by_platform.keys.sort == requested.sort
    [index_bytes, requested.map { |name| [name, by_platform.fetch(name)] }]
  end

  def blob(layout, descriptor)
    exact!(descriptor, %w[mediaType digest size]) unless descriptor.key?('platform')
    match = DIGEST.match(descriptor['digest'].to_s)
    raise unless match && descriptor['size'].is_a?(Integer) && descriptor['size'] >= 0
    path = File.join(layout, 'blobs', 'sha256', match[1])
    stat = File.lstat(path)
    raise unless stat.file? && !stat.symlink?
    bytes = File.binread(path)
    raise unless bytes.bytesize == descriptor['size'] && digest(bytes) == descriptor['digest']
    bytes
  end

  def validate_manifest(layout, bytes, platform)
    manifest = JSON.parse(bytes)
    exact!(manifest, %w[schemaVersion mediaType config layers])
    raise unless manifest['schemaVersion'] == 2 && manifest['mediaType'] == MANIFEST_MT
    raise unless manifest['config'].is_a?(Hash) && manifest['config']['mediaType'] == CONFIG_MT
    config = JSON.parse(blob(layout, manifest['config']))
    raise unless config.is_a?(Hash) && config['os'] == platform['os'] && config['architecture'] == platform['architecture']
    raise unless config['variant'] == platform['variant'] if platform.key?('variant') || config.key?('variant')
    raise unless manifest['layers'].is_a?(Array) && !manifest['layers'].empty?
    manifest['layers'].each do |layer|
      raise unless layer.is_a?(Hash) && LAYER_MTS.include?(layer['mediaType'])
      blob(layout, layer)
    end
  end

  def evaluate_platform(name, descriptor, layout, policy, keyring, waivers)
    base = verdict_base(name, descriptor['digest'])
    path = File.join(layout, 'evidence', "#{descriptor['digest'].delete_prefix('sha256:')}.provenance.json")
    return base.merge('status' => 'rejected', 'reasons' => ['PROVENANCE_MISSING']) unless File.file?(path)
    begin
      envelope = read_json(path)
      payload, signatures = validate_provenance(envelope)
    rescue StandardError
      return base.merge('status' => 'rejected', 'reasons' => ['PROVENANCE_MALFORMED'])
    end

    base['builder_id'] = payload['builder_id']
    base['source'] = payload['source_uri']
    base['commit'] = payload['commit']
    base['findings'] = payload['vulnerabilities']
    reasons = []
    reasons << 'SUBJECT_MISMATCH' unless payload['subject_digest'] == descriptor['digest']
    signers = contributing_signers(payload, signatures, keyring, policy)
    base['signers'] = signers.map { |x| x['key_id'] }.sort_by(&:b)
    counts = signers.map { |x| x['role'] }.tally
    threshold_ok = signers.length >= policy['signature_threshold'] &&
                   policy['role_minimums'].all? { |role, minimum| counts.fetch(role, 0) >= minimum }
    reasons << 'SIGNATURE_POLICY_UNMET' unless threshold_ok

    builder = policy['allowed_builders'].find { |x| x['builder_id'] == payload['builder_id'] }
    reasons << 'BUILDER_NOT_ALLOWED' unless builder
    reasons << 'SOURCE_NOT_ALLOWED' unless builder && payload['source_uri'].start_with?(builder['source_prefix'])
    reasons << 'REF_NOT_ALLOWED' unless builder && glob_match?(builder['ref_glob'], payload['ref'])
    reasons << 'COMMIT_INVALID' unless payload['commit'].match?(/\A[0-9a-f]{40}\z/)
    reasons << 'BUILD_TIME_INVALID' unless valid_build_times?(payload, policy)
    trusted = payload['materials'].all? do |material|
      policy['trusted_material_prefixes'].any? { |prefix| material['uri'].start_with?(prefix) }
    end
    reasons << 'MATERIAL_NOT_TRUSTED' unless trusted

    used = []
    unwaived = payload['vulnerabilities'].any? do |finding|
      next false unless %w[critical high].include?(finding['severity'])
      waiver = waivers['waivers'].find { |item| waiver_matches?(item, finding, name, payload, policy) }
      used << waiver['id'] if waiver
      waiver.nil?
    end
    reasons << 'VULNERABILITY_UNWAIVED' if unwaived
    base['waivers'] = used.uniq.sort_by(&:b)
    base['reasons'] = REASON_ORDER.select { |reason| reasons.include?(reason) }
    base['status'] = base['reasons'].empty? ? 'admitted' : 'rejected'
    base
  end

  def validate_provenance(envelope)
    exact!(envelope, %w[payload signatures])
    payload = envelope['payload']
    exact!(payload, %w[builder_id build_finished build_started commit materials ref source_uri
                       subject_digest vulnerabilities])
    %w[builder_id build_finished build_started commit ref source_uri subject_digest].each { |k| raise unless payload[k].is_a?(String) }
    raise unless payload['subject_digest'].match?(DIGEST)
    instant(payload['build_started']); instant(payload['build_finished'])
    raise unless payload['materials'].is_a?(Array) && !payload['materials'].empty?
    payload['materials'].each { |x| exact!(x, %w[digest uri]); raise unless x['uri'].is_a?(String) && x['digest'].to_s.match?(DIGEST) }
    raise unless payload['materials'].map { |x| x['uri'] }.sort_by(&:b) == payload['materials'].map { |x| x['uri'] }
    raise unless payload['materials'].map { |x| x['uri'] }.uniq.length == payload['materials'].length
    raise unless payload['vulnerabilities'].is_a?(Array)
    payload['vulnerabilities'].each do |x|
      exact!(x, %w[advisory package severity])
      raise unless x['advisory'].is_a?(String) && x['package'].is_a?(String) && %w[critical high medium low].include?(x['severity'])
    end
    pairs = payload['vulnerabilities'].map { |x| [x['advisory'], x['package']] }
    raise unless pairs == pairs.sort_by { |x| [x[0].b, x[1].b] } && pairs.uniq.length == pairs.length
    raise unless envelope['signatures'].is_a?(Array)
    envelope['signatures'].each do |x|
      exact!(x, %w[key_id signature]); raise unless x.values.all? { |v| v.is_a?(String) }
    end
    [payload, envelope['signatures']]
  end

  def contributing_signers(payload, signatures, keyring, policy)
    bytes = canonical(payload)
    finished = instant(payload['build_finished'])
    seen = {}
    signatures.filter_map do |signature|
      next if seen[signature['key_id']]
      seen[signature['key_id']] = true
      key = keyring['keys'].find { |item| item['key_id'] == signature['key_id'] }
      next unless key && key['builder_id'] == payload['builder_id'] && eligible?(key, finished)
      begin
        raw = Base64.strict_decode64(signature['signature'])
        public_key = OpenSSL::PKey.read(key['public_key_pem'])
        next unless raw.bytesize == 64 && public_key.verify(nil, raw, bytes)
      rescue StandardError
        next
      end
      key
    end
  end

  def eligible?(key, at)
    return false if at < instant(key['active_from'])
    return false if key['active_until'] && at >= instant(key['active_until'])
    return false if key['revoked_at'] && at >= instant(key['revoked_at'])
    true
  end

  def glob_match?(glob, value)
    pattern = Regexp.escape(glob).gsub('\\*', '.*')
    Regexp.new("\\A#{pattern}\\z").match?(value)
  end

  def valid_build_times?(payload, policy)
    started = instant(payload['build_started'])
    finished = instant(payload['build_finished'])
    started <= finished && finished <= instant(policy['evaluation_time'])
  end

  def waiver_matches?(item, finding, platform, payload, policy)
    now = instant(policy['evaluation_time'])
    start = instant(item['starts_at']); finish = instant(item['expires_at'])
    start < finish && start <= now && now < finish &&
      item['image'] == policy['image'] && item['platform'] == platform &&
      item['advisory'] == finding['advisory'] && item['package'] == finding['package'] &&
      item['builder_id'] == payload['builder_id'] && payload['source_uri'].start_with?(item['source_prefix']) &&
      (item['commit'].nil? || item['commit'] == payload['commit'])
  end

  def verdict_base(platform, manifest_digest)
    {'platform' => platform, 'manifest_digest' => manifest_digest, 'status' => 'rejected',
     'reasons' => [], 'builder_id' => nil, 'source' => nil, 'commit' => nil,
     'signers' => [], 'waivers' => [], 'findings' => []}
  end

  def write_output(out, image, index_digest, platforms)
    FileUtils.rm_rf(out); FileUtils.mkdir_p(File.join(out, 'admission'))
    platforms.each { |item| write_json(File.join(out, 'admission', "#{item['platform']}.json"), item) }
    report = {'image' => image, 'index_digest' => index_digest,
              'status' => platforms.all? { |x| x['status'] == 'admitted' } ? 'admitted' : 'rejected',
              'platforms' => platforms}
    report['evidence_digest'] = Digest::SHA256.hexdigest(canonical(platforms))
    write_json(File.join(out, 'report.json'), report)
  end

  def write_invalid(out, image)
    raise unless out
    FileUtils.rm_rf(out); FileUtils.mkdir_p(out)
    report = {'image' => image, 'index_digest' => nil, 'status' => 'rejected', 'reasons' => ['LAYOUT_INVALID'],
              'platforms' => [], 'evidence_digest' => Digest::SHA256.hexdigest('[]')}
    write_json(File.join(out, 'report.json'), report)
  end

  def digest(bytes) = "sha256:#{Digest::SHA256.hexdigest(bytes)}"

  def canonical(value)
    case value
    when Hash then '{' + value.keys.sort.map { |k| "#{JSON.generate(k)}:#{canonical(value[k])}" }.join(',') + '}'
    when Array then '[' + value.map { |x| canonical(x) }.join(',') + ']'
    else JSON.generate(value)
    end
  end

  def write_json(path, value) = File.binwrite(path, canonical(value) + "\n")

  def usage
    warn 'usage: forgegate evaluate --layout DIR --policy FILE --keyring FILE --waivers FILE --out DIR'
    2
  end
end
RUBY

chmod 0755 /app/bin/forgegate
ruby -c /app/lib/forgegate.rb
