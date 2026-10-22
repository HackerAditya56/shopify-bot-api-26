/**
 * User Agent Generator
 * Generates hundreds of thousands of unique mobile & desktop User Agents
 * Supports Android 4.3-14, Windows 7-11, Linux, macOS 10.7-14
 * Browsers: Chrome 90-131, Firefox 90-122, Edge 90-120, Safari 14-17
 */

class UserAgent {
    constructor() {
        this.androidVersion = null;
        this.rotationCounter = 0;
        this.rotationOrder = ['chrome', 'android', 'iphone', 'firefox', 'android', 'chrome', 'android', 'iphone'];
        
        this.windowsOS = [
            'Windows NT 6.{0-3}; Win64; x64',
            'Windows NT 10.0; Win64; x64',
            'Windows NT 11.0; Win64; x64'
        ];
        
        this.linuxOS = [
            'Linux x86_64',
            'Linux i686'
        ];
        
        this.macOS = [
            'Macintosh; Intel Mac OS X 10_{13-15}_{0-7}',
            'Macintosh; Intel Mac OS X 1{1-4}_{0-6}_{0-9}'
        ];
        
        this.androidVersions = ['8.0.0', '8.1.0', '9', '10', '11', '12', '12.1', '13', '14'];
        
        this.androidDevices = {
            '10': [
                'Pixel 4 Build/QQ3A.200805.001',
                'Pixel 4 XL Build/QQ3A.200805.001',
                'SM-G980F Build/QP1A.190711.020',
                'SM-G985F Build/QP1A.190711.020',
                'SM-N980F Build/QP1A.190711.020',
                'ONEPLUS 7 Pro Build/QKQ1.190716.003',
                'ONEPLUS 8 Build/QKQ1.190716.003'
            ],
            '11': [
                'Pixel 5 Build/RQ3A.210805.001',
                'Pixel 5a Build/RQ3A.210805.001',
                'SM-G991B Build/RP1A.200720.012',
                'SM-G996B Build/RP1A.200720.012',
                'SM-N998B Build/RP1A.200720.012',
                'ONEPLUS 9 Pro Build/RKQ1.201022.002'
            ],
            '12': [
                'Pixel 6 Build/SD1A.210817.015',
                'Pixel 6 Pro Build/SD1A.210817.015',
                'SM-S901B Build/SP1A.210812.016',
                'SM-S906B Build/SP1A.210812.016',
                'SM-S908B Build/SP1A.210812.016'
            ],
            '13': [
                'Pixel 7 Build/TQ3A.230805.001',
                'Pixel 7 Pro Build/TQ3A.230805.001',
                'SM-S921B Build/TP1A.220624.014',
                'SM-S926B Build/TP1A.220624.014',
                'SM-S928B Build/TP1A.220624.014'
            ],
            '14': [
                'Pixel 8 Build/UQ1A.231205.015',
                'Pixel 8 Pro Build/UQ1A.231205.015',
                'SM-S926B Build/UP1A.231005.007',
                'SM-S928B Build/UP1A.231005.007'
            ]
        };
        
        this.mobileIOS = {
            iphone: 'iPhone; CPU iPhone OS {12-17}_{0-6}_{0-3} like Mac OS X',
            ipad: 'iPad; CPU OS {12-17}_{0-6}_{0-3} like Mac OS X',
            ipod: 'iPod touch; CPU iPhone OS {12-15}_{0-4}_{0-2} like Mac OS X'
        };
    }
    
    randomInt(min, max) {
        return Math.floor(Math.random() * (max - min + 1)) + min;
    }
    
    processNumbers(str) {
        return str.replace(/\{(\d+)-(\d+)\}/g, (match, min, max) => {
            return this.randomInt(parseInt(min), parseInt(max));
        });
    }
    
    processSpinSyntax(str) {
        return str.replace(/\[([^\]]+)\]/g, (match, options) => {
            const choices = options.split('|');
            return choices[Math.floor(Math.random() * choices.length)];
        });
    }
    
    getOS(browser = null) {
        let osList;
        if (browser === 'explorer' || browser === 'edge') {
            osList = this.windowsOS;
        } else {
            osList = [...this.windowsOS, ...this.linuxOS, ...this.macOS];
        }
        
        let selected = osList[Math.floor(Math.random() * osList.length)];
        selected = this.processNumbers(selected);
        selected = this.processSpinSyntax(selected);
        
        if (Math.random() > 0.5) {
            selected += '; en-US';
        }
        return selected;
    }
    
    getMobileOS(os = null) {
        os = os?.toLowerCase();
        let template;
        
        if (os === 'iphone' || os === 'ipad' || os === 'ipod') {
            template = this.mobileIOS[os];
        } else if (os === 'android') {
            this.androidVersion = this.androidVersions[Math.floor(Math.random() * this.androidVersions.length)];
            const version = this.androidVersion.split('.')[0];
            const devices = this.androidDevices[version] || this.androidDevices['14'];
            const device = devices[Math.floor(Math.random() * devices.length)];
            return `Linux; Android ${this.androidVersion}; ${device}`;
        } else {
            // Random mobile OS
            const all = [...Object.values(this.mobileIOS), 'android'];
            const choice = all[Math.floor(Math.random() * all.length)];
            if (choice === 'android') {
                return this.getMobileOS('android');
            }
            template = choice;
        }
        
        return this.processNumbers(template);
    }
    
    chromeVersion() {
        const major = this.randomInt(90, 131);
        const build = this.randomInt(4000, 7000);
        const patch = this.randomInt(100, 200);
        return `${major}.0.${build}.${patch}`;
    }
    
    firefoxVersion() {
        return `${this.randomInt(90, 122)}.0`;
    }
    
    edgeVersion() {
        const major = this.randomInt(90, 120);
        const build = this.randomInt(1000, 2000);
        const patch = this.randomInt(10, 99);
        return `${major}.0.${build}.${patch}`;
    }
    
    generate(type = null) {
        if (type === null) {
            type = this.rotationOrder[this.rotationCounter % this.rotationOrder.length];
            this.rotationCounter++;
        }
        
        type = type.toLowerCase();
        
        switch (type) {
            case 'chrome':
                return `Mozilla/5.0 (${this.getOS('chrome')}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${this.chromeVersion()} Safari/537.36`;
            
            case 'firefox':
                return `Mozilla/5.0 (${this.getOS('firefox')}) Gecko/20100101 Firefox/${this.firefoxVersion()}`;
            
            case 'edge':
            case 'explorer':
                return `Mozilla/5.0 (${this.getOS('windows')}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${this.chromeVersion()} Safari/537.36 Edg/${this.edgeVersion()}`;
            
            case 'android':
                return `Mozilla/5.0 (${this.getMobileOS('android')}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/${this.chromeVersion()} Mobile Safari/537.36`;
            
            case 'iphone':
            case 'ipad':
            case 'ipod':
                const version = this.randomInt(14, 17);
                const minor = this.randomInt(0, 6);
                return `Mozilla/5.0 (${this.getMobileOS(type)}) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/${version}.${minor} Mobile/15E148 Safari/604.1`;
            
            case 'mobile':
                const mobileTypes = ['android', 'iphone'];
                return this.generate(mobileTypes[Math.floor(Math.random() * mobileTypes.length)]);
            
            case 'windows':
            case 'mac':
            case 'linux':
                const browsers = ['chrome', 'firefox'];
                if (type === 'windows') browsers.push('edge');
                return this.generate(browsers[Math.floor(Math.random() * browsers.length)]);
            
            default:
                return this.generate('chrome');
        }
    }
}

export default UserAgent;
