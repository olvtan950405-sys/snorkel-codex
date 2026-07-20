# frozen_string_literal: true

require 'digest'
require 'fileutils'
require 'json'

module ForgeGate
  module_function

  # This migration placeholder deliberately trusts descriptor annotations and
  # emits an allow-shaped result. The contracts describe the actual trust gate.
  def run(argv)
    return usage unless argv.shift == 'evaluate'

    options = parse_options(argv)
    required = %w[layout policy keyring waivers out]
    return usage unless required.all? { |name| options[name] }

    index = JSON.parse(File.read(File.join(options['layout'], 'index.json')))
    policy = JSON.parse(File.read(options['policy']))
    FileUtils.rm_rf(options['out'])
    FileUtils.mkdir_p(File.join(options['out'], 'admission'))

    platforms = index.fetch('manifests', []).map do |descriptor|
      platform = descriptor.fetch('platform', {})
      name = [platform['os'], platform['architecture'], platform['variant']].compact.join('-')
      {
        'platform' => name,
        'manifest_digest' => descriptor['digest'],
        'status' => 'admitted',
        'reasons' => [],
        'builder_id' => descriptor.dig('annotations', 'builder'),
        'source' => descriptor.dig('annotations', 'source'),
        'commit' => descriptor.dig('annotations', 'commit'),
        'signers' => [],
        'waivers' => []
      }
    end

    report = {
      'image' => policy['image'],
      'index_digest' => "sha256:#{Digest::SHA256.file(File.join(options['layout'], 'index.json')).hexdigest}",
      'status' => platforms.all? { |item| item['status'] == 'admitted' } ? 'admitted' : 'rejected',
      'platforms' => platforms.sort_by { |item| item['platform'].b }
    }
    report['evidence_digest'] = Digest::SHA256.hexdigest(canonical(report['platforms']))
    write_json(File.join(options['out'], 'report.json'), report)
    platforms.each do |item|
      write_json(File.join(options['out'], 'admission', "#{item['platform']}.json"), item)
    end
    0
  rescue StandardError => e
    warn "forgegate: #{e.message}"
    2
  end

  def parse_options(argv)
    result = {}
    until argv.empty?
      flag = argv.shift
      return {} unless flag&.start_with?('--') && !argv.empty?

      result[flag.delete_prefix('--')] = argv.shift
    end
    result
  end

  def canonical(value)
    case value
    when Hash
      '{' + value.keys.sort.map { |key| "#{JSON.generate(key)}:#{canonical(value[key])}" }.join(',') + '}'
    when Array then '[' + value.map { |item| canonical(item) }.join(',') + ']'
    else JSON.generate(value)
    end
  end

  def write_json(path, value)
    File.write(path, canonical(value) + "\n")
  end

  def usage
    warn 'usage: forgegate evaluate --layout DIR --policy FILE --keyring FILE --waivers FILE --out DIR'
    2
  end
end
